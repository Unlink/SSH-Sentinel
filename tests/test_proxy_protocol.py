"""Real socket tests for the opt-in trusted proxy boundary."""
import asyncio
import json
import socket
from pathlib import Path
import importlib.util

import asyncssh
import pytest

from app.common.config import Settings
from app.sensor.server import start_sensor


def events(settings):
    return [json.loads(line) for p in settings.event_dir.glob('*.jsonl') for line in p.read_text().splitlines()]


@pytest.fixture
async def proxied(tmp_path):
    settings = Settings(event_dir=tmp_path/'events', key_dir=tmp_path/'keys',
                        ssh_host='127.0.0.1', ssh_port=0, proxy_protocol=True)
    server = await start_sensor(settings)
    yield server, settings
    server.close()
    await server.wait_closed()


@pytest.mark.parametrize('header,expected', [
    (b'PROXY TCP4 203.0.113.9 192.0.2.1 12345 2222\r\n', '203.0.113.9'),
    (b'PROXY TCP6 2001:db8::9 2001:db8::1 12345 2222\r\n', '2001:db8::9'),
])
async def test_header_fragmentation_and_full_ssh(proxied, header, expected):
    server, settings = proxied
    sock = socket.socket()
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    await loop.sock_connect(sock, ('127.0.0.1', server.get_port()))
    for fragment in (header[:7], header[7:]):
        await loop.sock_sendall(sock, fragment)
        await asyncio.sleep(0.01)
    async with asyncssh.connect(sock=sock, username='test', password='synthetic', known_hosts=None) as conn:
        assert (await conn.run('whoami')).stdout == 'test\n'
    await asyncio.sleep(0.05)
    assert events(settings)
    assert {e['ip'] for e in events(settings)} == {expected}


@pytest.mark.parametrize('header', [
    b'SSH-2.0-client\r\n', b'PROXY UNKNOWN\r\n',
    b'PROXY TCP4 999.1.1.1 192.0.2.1 1 2\r\n',
    b'PROXY TCP4 ::1 192.0.2.1 1 2\r\n',
    b'PROXY TCP4 203.0.113.9 192.0.2.1 65536 2\r\n',
    b'PROXY '+b'x'*103, b'PROXY TCP4 1.1.1.1 2.2.2.2 1 2\n',
])
async def test_invalid_headers_rejected_without_ssh_or_events(proxied, header):
    server, settings = proxied
    reader, writer = await asyncio.open_connection('127.0.0.1', server.get_port())
    writer.write(header)
    await writer.drain()
    assert await asyncio.wait_for(reader.read(100), 1) == b''
    writer.close()
    await writer.wait_closed()
    assert events(settings) == []


async def test_native_proxy_overrides_client_claims(proxied):
    spec = importlib.util.spec_from_file_location('windows_proxy', Path(__file__).resolve().parents[1]/'scripts/windows_proxy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    backend, settings = proxied
    proxy = module.Proxy(backend_port=backend.get_port(), max_connections=1, session_seconds=2)
    listener = await asyncio.start_server(proxy.handle, '127.0.0.1', 0)
    port = listener.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
    assert (await asyncio.wait_for(reader.readline(), 1)).startswith(b'SSH-2.0-')
    writer.write(b'PROXY TCP4 203.0.113.99 192.0.2.1 123 2222\r\n')
    await writer.drain()
    second_reader, second_writer = await asyncio.open_connection('127.0.0.1', port)
    assert await asyncio.wait_for(second_reader.read(), 1) == b''
    second_writer.close()
    await second_writer.wait_closed()
    writer.close()
    await writer.wait_closed()
    await asyncio.sleep(0.1)
    async with asyncssh.connect('127.0.0.1', port, username='native', password='synthetic', known_hosts=None) as conn:
        assert (await conn.run('whoami')).stdout == 'native\n'
    listener.close()
    await listener.wait_closed()
    await asyncio.sleep(0.05)
    assert {e['ip'] for e in events(settings)} == {'127.0.0.1'}
    assert proxy.active == 0


async def test_header_timeout_and_pending_connection_cap(proxied):
    server, settings = proxied
    sockets = [await asyncio.open_connection('127.0.0.1', server.get_port())
               for _ in range(settings.max_connections)]
    reader, writer = await asyncio.open_connection('127.0.0.1', server.get_port())
    assert await asyncio.wait_for(reader.read(), 1) == b''
    writer.close()
    await writer.wait_closed()
    # Even a silent trusted peer cannot retain a pending header indefinitely.
    assert await asyncio.wait_for(sockets[0][0].read(), 6) == b''
    for _, stream in sockets:
        stream.close()
        await stream.wait_closed()
    assert events(settings) == []


async def test_header_and_ssh_bytes_in_same_packet(proxied):
    server, settings = proxied
    reader, writer = await asyncio.open_connection('127.0.0.1', server.get_port())
    writer.write(b'PROXY TCP4 203.0.113.8 192.0.2.1 123 2222\r\nSSH-2.0-test\r\n')
    await writer.drain()
    assert (await asyncio.wait_for(reader.readline(), 1)).startswith(b'SSH-2.0-')
    writer.close()
    await writer.wait_closed()
    await asyncio.sleep(0.05)
    assert {e['ip'] for e in events(settings)} == {'203.0.113.8'}


async def test_native_proxy_lifetime_releases_capacity(proxied):
    spec = importlib.util.spec_from_file_location('windows_proxy', Path(__file__).resolve().parents[1]/'scripts/windows_proxy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    backend, _ = proxied
    proxy = module.Proxy(backend_port=backend.get_port(), session_seconds=0.1)
    listener = await asyncio.start_server(proxy.handle, '127.0.0.1', 0)
    reader, writer = await asyncio.open_connection('127.0.0.1', listener.sockets[0].getsockname()[1])
    assert (await reader.readline()).startswith(b'SSH-2.0-')
    assert await asyncio.wait_for(reader.read(), 1) == b''
    await asyncio.sleep(0.05)
    assert proxy.active == 0
    writer.close()
    await writer.wait_closed()
    listener.close()
    await listener.wait_closed()
