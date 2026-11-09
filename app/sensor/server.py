"""Public SSH protocol endpoint. All sessions use FakeShell exclusively."""
import asyncio
import contextlib
import json
import logging
import os
import time
from uuid import uuid4

import asyncssh

from app.common.config import Settings
from app.sensor.authentication import authenticate
from app.sensor.channel import HoneypotChannel
from app.sensor.events import EventWriter
from app.sensor.fake_shell import FakeShell
from app.sensor.transport import BoundedSSHConnection
from app.sensor.proxy_protocol import ProxyProtocol


class HoneypotSession(asyncssh.SSHServerSession):
    def __init__(self, owner):
        self.owner = owner
        self.shell = FakeShell(owner.username)
        self.buffer = ''
        self.command = None
        self.count = 0
        self.started = time.monotonic()
        self.closed = False
        self.output_bytes = 0
        self.input_bytes = 0

    def connection_made(self, chan):
        self.chan = chan

    def pty_requested(self, term_type, term_size, term_modes):
        return True

    def shell_requested(self):
        return True

    def exec_requested(self, command):
        if len(command) > self.owner.settings.max_line or command.lstrip().startswith('scp'):
            self.owner.event('denied', request='exec', command=command)
            return False
        self.command = command
        return True

    def subsystem_requested(self, subsystem):
        self.owner.event('denied', request='subsystem', subsystem=subsystem)
        return False

    def session_started(self):
        self.owner.event('shell_start', username=self.owner.username, mode='exec' if self.command is not None else 'interactive')
        if self.command is not None:
            self.run(self.command)
            self.finish()
        else:
            self.send('Linux srv01 6.12.0\n' + self.shell.prompt)

    def send(self, text):
        if self.closed:
            return
        size = len(text.encode('utf-8'))
        if self.output_bytes + size > 65536:
            self.owner.event('limit', limit='output')
            self.finish()
            return
        self.output_bytes += size
        self.chan.write(text)

    def run(self, command):
        if self.closed:
            return
        self.count += 1
        self.owner.event('command', username=self.owner.username, command=command)
        output, done = self.shell.execute(command)
        self.send(output)
        if done or self.count >= self.owner.settings.max_commands:
            self.finish()

    def data_received(self, data, datatype):
        self.input_bytes += len(data.encode('utf-8'))
        if self.input_bytes > 1024 * 1024:
            self.owner.event('limit', limit='input')
            self.finish()
            return
        for char in data:
            if self.closed:
                return
            if char in '\r\n':
                self.run(self.buffer)
                self.buffer = ''
                if not self.closed:
                    self.send(self.shell.prompt)
            elif char in ('\x08', '\x7f'):
                self.buffer = self.buffer[:-1]
            elif char == '\x03':
                self.buffer = ''
                self.send('^C\n' + self.shell.prompt)
            else:
                self.buffer += char
                if len(self.buffer) > self.owner.settings.max_line:
                    self.owner.event('limit', limit='line')
                    self.finish()

    def finish(self):
        if not self.closed:
            self.closed = True
            self.chan.exit(0)

    def eof_received(self):
        self.finish()
        return False

    def connection_lost(self, exc):
        self.closed = True
        self.owner.event('shell_end', duration=round(time.monotonic() - self.started, 3), commands=self.count)


class HoneypotServer(asyncssh.SSHServer):
    def __init__(self, settings, writer, live):
        self.settings, self.writer, self.live = settings, writer, live
        self.id = str(uuid4())
        self.username = ''
        self.authenticated = False
        self.handshake = False
        self.attempts = 0
        self.channels = 0
        self.started = time.monotonic()
        self.timer = None

    def event(self, kind, **data):
        self.writer.emit(kind, self.id, self.ip, **data)

    def connection_made(self, conn):
        self.conn = conn
        conn.sentinel_owner = self
        self.ip = conn.get_extra_info('peername')[0]
        self.event('connection')
        if len(self.live) >= self.settings.max_connections:
            self.event('limit', limit='connections')
            conn.abort()
            return
        self.live.add(self)
        self.timer = asyncio.get_running_loop().call_later(self.settings.session_seconds, self.expire)

    def expire(self):
        self.event('limit', limit='duration')
        self.conn.abort()

    def begin_auth(self, username):
        self.username = username
        if not self.handshake:
            self.handshake = True
            self.event('handshake', banner=self.conn.get_extra_info('client_version', ''), username=username)
        return True

    def password_auth_supported(self):
        return True

    def public_key_auth_supported(self):
        return True

    def validate_public_key(self, username, key):
        self.attempts += 1
        self.event('auth_attempt', username=username, method='publickey',
                   fingerprint=key.get_fingerprint(), accepted=False, stage='key_probe')
        if self.attempts >= 5:
            self.conn.abort()
        return False

    def validate_password(self, username, password):
        self.attempts += 1
        accepted = authenticate(self.writer, self.settings, self.id, self.ip, username, password)
        if self.attempts >= 5 and not accepted:
            self.conn.abort()
        return accepted

    def auth_completed(self):
        self.authenticated = True

    def session_requested(self):
        # Lifetime channel budget prevents reopening many channels on one transport.
        if self.channels >= 1:
            self.event('denied', request='additional_session')
            return False
        self.channels += 1
        return HoneypotChannel(self), HoneypotSession(self)

    def connection_requested(self, *args):
        self.event('denied', request='forwarding')
        return False

    def server_requested(self, *args):
        self.event('denied', request='remote_forwarding')
        return False

    def unix_connection_requested(self, *args):
        return False

    def unix_server_requested(self, *args):
        return False

    def connection_lost(self, exc):
        if self.timer:
            self.timer.cancel()
        self.live.discard(self)
        self.event('disconnect', authenticated=self.authenticated, handshake=self.handshake,
                   banner=self.conn.get_extra_info('client_version', ''),
                   duration=round(time.monotonic() - self.started, 3))


async def start_sensor(settings):
    settings.key_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    key_path = settings.key_dir / 'ssh_host_ed25519_key'
    if not key_path.exists():
        key = asyncssh.generate_private_key('ssh-ed25519')
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(key.export_private_key())
    writer = EventWriter(settings.event_dir, settings.rotate_bytes, settings.spool_bytes, settings.retention_days)
    live = set()
    loop = asyncio.get_running_loop()
    options = asyncssh.SSHServerConnectionOptions(
        server_factory=lambda: HoneypotServer(settings, writer, live),
        config=[], server_host_keys=[str(key_path)],
        server_version='OpenSSH_9.9p2', login_timeout=settings.login_seconds,
        encoding='utf-8', errors='replace', line_editor=False,
        compression_algs=None,
        allow_scp=False, sftp_factory=None, agent_forwarding=False, x11_forwarding=False,
        max_pktsize=32768, window=65536)
    pending = set()
    def protocol_factory():
        factory = lambda: BoundedSSHConnection(loop, options)
        return ProxyProtocol(factory, pending, settings.max_connections) if settings.proxy_protocol else factory()

    listener = await loop.create_server(protocol_factory,
                                        settings.ssh_host, settings.ssh_port, backlog=64)
    server = asyncssh.SSHAcceptor(listener, options)
    server.event_writer = writer
    server.live_connections = live
    return server


async def main():
    settings = Settings.from_env()
    server = await start_sensor(settings)
    try:
        while True:
            try:
                server.event_writer.maintain()
                status = {'time': time.time(), 'healthy': server.event_writer.healthy}
                (settings.key_dir / 'health.json').write_text(json.dumps(status))
            except OSError:
                logging.error('Sensor maintenance failed')
            await asyncio.sleep(10)
    finally:
        for conn in tuple(server.live_connections):
            conn.conn.abort()
        server.close()
        await server.wait_closed()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
