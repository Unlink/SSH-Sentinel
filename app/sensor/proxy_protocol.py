"""Mandatory PROXY v1 on an explicitly trusted, private backend only.

PROXY metadata is unauthenticated. Never enable this on a public binding.
"""
import asyncio
import ipaddress


class PeerTransport:
    def __init__(self, transport, peer):
        self.transport, self.peer = transport, peer

    def get_extra_info(self, name, default=None):
        return self.peer if name == 'peername' else self.transport.get_extra_info(name, default)

    def __getattr__(self, name):
        return getattr(self.transport, name)


class ProxyProtocol(asyncio.Protocol):
    def __init__(self, factory, connections, limit):
        self.factory, self.connections, self.limit = factory, connections, limit
        self.inner = None
        self.buffer = b''
        self.timer = None
        self.closed = False

    def connection_made(self, transport):
        self.transport = transport
        if len(self.connections) >= self.limit:
            self.reject()
            return
        self.connections.add(self)
        self.timer = asyncio.get_running_loop().call_later(5, self.reject)

    def reject(self):
        self.closed = True
        self.buffer = b''
        self.transport.abort()

    def data_received(self, data):
        if self.closed:
            return
        if self.inner:
            self.inner.data_received(data)
            return
        old_length = len(self.buffer)
        prefix = self.buffer + data[:108-old_length]
        end = prefix.find(b'\r\n')
        if end < 0:
            if len(prefix) >= 108 or b'\n' in prefix:
                self.reject()
            else:
                self.buffer = prefix
            return
        try:
            fields = prefix[:end].decode('ascii').split(' ')
            if len(fields) != 6 or fields[0] != 'PROXY' or fields[1] not in ('TCP4', 'TCP6'):
                raise ValueError('Invalid PROXY header')
            version = 4 if fields[1] == 'TCP4' else 6
            source, destination = (ipaddress.ip_address(value) for value in fields[2:4])
            if source.version != version or destination.version != version:
                raise ValueError('Address family mismatch')
            for port in fields[4:]:
                if not port.isascii() or not port.isdecimal() or len(port) > 5 or not 0 <= int(port) <= 65535:
                    raise ValueError('Invalid port')
            peer = (str(source), int(fields[4]))
        except (ValueError, UnicodeError):
            self.reject()
            return
        self.buffer = b''
        self.timer.cancel()
        self.inner = self.factory()
        self.inner.connection_made(PeerTransport(self.transport, peer))
        remainder = data[end+2-old_length:]
        if remainder:
            self.inner.data_received(remainder)

    def connection_lost(self, exc):
        self.connections.discard(self)
        if self.timer:
            self.timer.cancel()
        if self.inner:
            self.inner.connection_lost(exc)

    def eof_received(self):
        if self.inner:
            return self.inner.eof_received()
        self.reject()
        return False

    def pause_writing(self):
        if self.inner:
            self.inner.pause_writing()

    def resume_writing(self):
        if self.inner:
            self.inner.resume_writing()
