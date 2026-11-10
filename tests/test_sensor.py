import asyncio
import json

import asyncssh
import pytest

from app.common.config import Settings
from app.sensor.server import start_sensor


def records(path):
    return [json.loads(line) for f in path.glob('*.jsonl') for line in f.read_text().splitlines()]


@pytest.fixture
async def sensor(tmp_path):
    settings = Settings(event_dir=tmp_path / 'events', key_dir=tmp_path / 'keys',
                        ssh_host='127.0.0.1', ssh_port=0, max_line=128)
    server = await start_sensor(settings)
    yield server, settings
    server.close()
    await server.wait_closed()


async def test_password_capture_exec_and_denied_channels(sensor, tmp_path):
    server, settings = sensor
    async with asyncssh.connect('127.0.0.1', server.get_port(), username='intruder',
                                password='hunter2', known_hosts=None) as conn:
        result = await conn.run('whoami')
        assert result.stdout == 'intruder\n'
        reader, writer = await conn.open_connection('127.0.0.1', 8080)
        writer.write_eof()
        assert await asyncio.wait_for(reader.read(), 1) == b''
        writer.close()
        await writer.wait_closed()
        with pytest.raises(asyncssh.Error):
            await conn.start_sftp_client()
        with pytest.raises(asyncssh.Error):
            await conn.run('scp -t /tmp/file')
    await asyncio.sleep(0.05)
    events = records(settings.event_dir)
    assert any(e['kind'] == 'connection' for e in events)
    auth = next(e for e in events if e['kind'] == 'auth_attempt')
    assert auth['data']['password'] == 'hunter2'
    assert auth['data']['username'] == 'intruder'
    assert any(e['kind'] == 'command' and e['data']['command'] == 'whoami' for e in events)
    assert any(e['kind'] == 'disconnect' and e['data']['authenticated'] for e in events)


async def test_plain_tcp_disconnect_is_recorded(sensor):
    server, settings = sensor
    _, writer = await asyncio.open_connection('127.0.0.1', server.get_port())
    writer.close()
    await writer.wait_closed()
    await asyncio.sleep(0.05)
    events = records(settings.event_dir)
    assert any(e['kind'] == 'connection' for e in events)
    assert any(e['kind'] == 'disconnect' and not e['data']['authenticated'] for e in events)


async def test_interactive_limit_and_single_channel(sensor):
    server, settings = sensor
    async with asyncssh.connect('127.0.0.1', server.get_port(), username='root',
                                password='secret', known_hosts=None) as conn:
        process = await conn.create_process(term_type='xterm')
        with pytest.raises(asyncssh.ChannelOpenError):
            await conn.create_process()
        process.stdin.write('x' * 129 + '\n')
        await asyncio.wait_for(process.wait_closed(), 2)
    assert any(e['kind'] == 'limit' for e in records(settings.event_dir))


async def test_password_capture_can_be_disabled(tmp_path):
    settings = Settings(event_dir=tmp_path / 'events', key_dir=tmp_path / 'keys',
                        ssh_host='127.0.0.1', ssh_port=0, log_passwords=False)
    server = await start_sensor(settings)
    try:
        async with asyncssh.connect('127.0.0.1', server.get_port(), username='root',
                                    password='secret', known_hosts=None):
            pass
        await asyncio.sleep(0.05)
        event = next(e for e in records(settings.event_dir) if e['kind'] == 'auth_attempt')
        assert 'password' not in event['data']
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.parametrize('channel_request', ['sftp', 'scp', 'remote_forward'])
async def test_forbidden_request_as_first_channel(sensor, channel_request):
    server, settings = sensor
    async with asyncssh.connect('127.0.0.1', server.get_port(), username='root',
                                password='test', known_hosts=None) as conn:
        with pytest.raises((asyncssh.Error, asyncssh.ChannelListenError)):
            if channel_request == 'sftp':
                await conn.start_sftp_client()
            elif channel_request == 'scp':
                await conn.run('scp -t /tmp/file')
            else:
                await conn.forward_remote_port('127.0.0.1', 0, '127.0.0.1', 80)
    assert any(e['kind'] == 'denied' for e in records(settings.event_dir))


async def test_public_key_attempt_is_recorded(sensor):
    server, settings = sensor
    key = asyncssh.generate_private_key('ssh-ed25519')
    with pytest.raises(asyncssh.PermissionDenied):
        await asyncssh.connect('127.0.0.1', server.get_port(), username='scanner',
                               client_keys=[key], agent_path=None, known_hosts=None)
    await asyncio.sleep(0.05)
    assert any(e['kind'] == 'auth_attempt' and e['data']['method'] == 'publickey'
               and not e['data']['accepted'] for e in records(settings.event_dir))


async def test_connection_count_and_absolute_timeout(tmp_path):
    settings = Settings(event_dir=tmp_path / 'events', key_dir=tmp_path / 'keys',
                        ssh_host='127.0.0.1', ssh_port=0, max_connections=1, session_seconds=1)
    server = await start_sensor(settings)
    writers = []
    try:
        for _ in range(5):
            _, writer = await asyncio.open_connection('127.0.0.1', server.get_port())
            writers.append(writer)
        await asyncio.sleep(1.1)
        limits = [e['data']['limit'] for e in records(settings.event_dir) if e['kind'] == 'limit']
        assert limits.count('connections') == 4
        assert 'duration' in limits
    finally:
        for writer in writers:
            writer.close()
            await writer.wait_closed()
        server.close()
        await server.wait_closed()


async def test_session_output_is_bounded(sensor):
    server, settings = sensor
    async with asyncssh.connect('127.0.0.1', server.get_port(), username='root',
                                password='test', known_hosts=None) as conn:
        process = await conn.create_process()
        # Ctrl-C does not consume the command budget and must still have an output cap.
        process.stdin.write('\x03' * 10000 + 'exit\n')
        result = await asyncio.wait_for(process.wait(), 3)
        assert len(result.stdout.encode()) <= 65536
    assert any(e['kind'] == 'limit' and e['data']['limit'] == 'output'
               for e in records(settings.event_dir))


async def test_environment_requests_are_not_retained(sensor):
    server, _ = sensor
    async with asyncssh.connect('127.0.0.1', server.get_port(), username='root',
                                password='test', known_hosts=None) as conn:
        process = await conn.create_process(env={f'KEY{i}': 'X' * 16384 for i in range(30)})
        owner = next(iter(server.live_connections))
        # Read actual retained server channel state, not a mocked library callback.
        channel = next(iter(owner.conn._channels.values()))
        assert dict(channel.get_environment()) == {}
        from asyncssh.packet import String
        assert not await process.channel._make_request(b'env', String(b'AFTER_START'), String(b'not retained'))
        assert dict(channel.get_environment()) == {}
        process.stdin.write('exit\n')
        await process.wait_closed()


async def test_environment_request_flood_closes_transport(sensor):
    server, settings = sensor
    async with asyncssh.connect('127.0.0.1', server.get_port(), username='root',
                                password='test', known_hosts=None) as conn:
        with pytest.raises((asyncssh.Error, OSError)):
            await conn.create_process(env={f'KEY{i}': 'value' for i in range(300)})
    assert any(e['kind'] == 'limit' and e['data']['limit'] == 'channel_requests'
               for e in records(settings.event_dir))


async def test_transport_compression_cannot_bypass_input_limits(sensor):
    server, _ = sensor
    async with asyncssh.connect('127.0.0.1', server.get_port(), username='root',
                                password='test', known_hosts=None,
                                compression_algs=['zlib@openssh.com', 'zlib', 'none']) as conn:
        assert conn.get_extra_info('send_compression') == 'none'
        assert conn.get_extra_info('recv_compression') == 'none'


async def test_transport_backpressure_aborts_connection(sensor):
    server, settings = sensor
    async with asyncssh.connect('127.0.0.1', server.get_port(), username='root',
                                password='test', known_hosts=None) as conn:
        owner = next(iter(server.live_connections))
        # asyncio invokes this exact callback when transport output exceeds its high water mark.
        owner.conn.pause_writing()
        await asyncio.sleep(.05)
        assert any(e['kind'] == 'limit' and e['data']['limit'] == 'transport_output'
                   for e in records(settings.event_dir))
        await asyncio.wait_for(conn.wait_closed(), 1)


async def test_connection_wide_budget_covers_ignore_packets(sensor):
    from asyncssh.constants import MSG_IGNORE
    from asyncssh.packet import String
    server, settings = sensor
    async with asyncssh.connect('127.0.0.1', server.get_port(), username='root',
                                password='test', known_hosts=None) as conn:
        for _ in range(80):
            conn.send_packet(MSG_IGNORE, String(b'x' * 65536))
        await asyncio.sleep(.2)
        assert any(e['kind'] == 'limit' and e['data']['limit'] == 'transport_input'
                   for e in records(settings.event_dir))


async def test_nonreading_peer_cannot_accumulate_global_replies(sensor):
    import socket
    from asyncssh.constants import MSG_GLOBAL_REQUEST
    from asyncssh.packet import Boolean, String
    server, settings = sensor
    async with asyncssh.connect('127.0.0.1', server.get_port(), username='root',
                                password='test', known_hosts=None) as conn:
        owner = next(iter(server.live_connections))
        owner.conn._transport.get_extra_info('socket').setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        client_transport = conn._transport
        client_transport.pause_reading()
        try:
            for i in range(30000):
                if conn.is_closed():
                    break
                conn.send_packet(MSG_GLOBAL_REQUEST, String(b'keepalive@openssh.com'), Boolean(True))
                if i % 256 == 0:
                    await asyncio.sleep(0)
            for _ in range(100):
                if not server.live_connections:
                    break
                await asyncio.sleep(.01)
            assert any(e['kind'] == 'limit' and e['data']['limit'] == 'transport_output'
                       for e in records(settings.event_dir))
            assert not server.live_connections
        finally:
            client_transport.resume_reading()


