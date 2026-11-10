"""Actual SSH channels must simulate forwarding without DNS or outbound TCP."""
import asyncio
import base64
import json

import asyncssh
import pytest

from app.common.config import Settings
from app.sensor.server import start_sensor
from app.common.schemas import validate_event


def records(settings):
    return [json.loads(line) for p in settings.event_dir.glob('*.jsonl') for line in p.read_text().splitlines()]


@pytest.fixture
async def sensor(tmp_path):
    settings=Settings(event_dir=tmp_path/'events',key_dir=tmp_path/'keys',ssh_host='127.0.0.1',ssh_port=0)
    server=await start_sensor(settings)
    yield server,settings
    for owner in tuple(server.live_connections):
        owner.conn.abort()
    server.close()
    await server.wait_closed()
    await asyncio.sleep(0.02)


async def test_forwarding_captures_target_without_dialing_or_resolving(sensor, monkeypatch):
    server,settings=sensor
    accepted=[]
    def connected(reader,writer):
        accepted.append(True)
        writer.close()
    target=await asyncio.start_server(connected,'127.0.0.1',0)
    port=target.sockets[0].getsockname()[1]
    baseline_reader,baseline_writer=await asyncio.open_connection('127.0.0.1',port)
    assert await baseline_reader.read()==b''
    baseline_writer.close()
    await baseline_writer.wait_closed()
    assert accepted==[True]
    accepted.clear()
    try:
        async with asyncssh.connect('127.0.0.1',server.get_port(),username='admin',password='',known_hosts=None) as conn:
            async def forbidden_dns(*args,**kwargs):
                pytest.fail('Virtual forwarding attempted DNS resolution')
            monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',forbidden_dns)
            for host,dest_port in [('127.0.0.1',port),('probe.invalid',443)]:
                reader,writer=await conn.open_connection(host,dest_port,orig_host='203.0.113.99',orig_port=1234,encoding=None)
                writer.write(b'GET / HTTP/1.1\r\nHost: probe.invalid\r\n\r\n')
                writer.write_eof()
                assert await asyncio.wait_for(reader.read(),1)==b''
                writer.close()
                await writer.wait_closed()
            assert (await conn.run('whoami')).stdout=='admin\n'
        await asyncio.sleep(0.05)
        assert accepted==[]
    finally:
        target.close()
        await target.wait_closed()
    rows=records(settings)
    for row in rows: validate_event(row)
    opens=[e for e in rows if e['kind']=='forward_open']
    closes=[e for e in rows if e['kind']=='forward_close']
    assert len(opens)==len(closes)==2
    assert opens[1]['data']['destination_host']=='probe.invalid'
    assert opens[0]['data']['destination_port']==port
    assert opens[0]['data']['claimed_origin_host']=='203.0.113.99'
    assert {e['ip'] for e in opens}=={'127.0.0.1'}
    assert all(e['data']['simulated'] for e in opens)
    assert base64.b64decode(closes[0]['data']['sample_base64']).startswith(b'GET / HTTP/1.1')


async def test_forward_sample_is_binary_safe_bounded_and_closed_at_input_limit(sensor):
    server,settings=sensor
    payload=b'\x00\xff<script>evil</script>'+b'x'*20000
    async with asyncssh.connect('127.0.0.1',server.get_port(),username='root',password='test',known_hosts=None) as conn:
        reader,writer=await conn.open_connection('192.0.2.1',80,encoding=None)
        writer.write(payload[:100])
        await writer.drain()
        writer.write(payload[100:])
        assert await asyncio.wait_for(reader.read(),2)==b''
        writer.close()
        await writer.wait_closed()
    await asyncio.sleep(0.05)
    close=next(e for e in records(settings) if e['kind']=='forward_close')['data']
    assert base64.b64decode(close['sample_base64'])==payload[:2048]
    assert close['sample_truncated'] is True
    assert close['reason']=='input_limit'
    assert 16384<=close['received_bytes']<=20480


async def test_forward_concurrency_and_lifetime_limits(sensor):
    server,settings=sensor
    async with asyncssh.connect('127.0.0.1',server.get_port(),username='root',password='test',known_hosts=None) as conn:
        first=await conn.open_connection('192.0.2.1',80,encoding=None)
        second=await conn.open_connection('192.0.2.2',80,encoding=None)
        with pytest.raises(asyncssh.ChannelOpenError):
            await conn.open_connection('192.0.2.3',80,encoding=None)
        for reader,writer in (first,second):
            writer.close()
            await writer.wait_closed()
        for _ in range(6):
            reader,writer=await conn.open_connection('192.0.2.1',80,encoding=None)
            writer.write_eof()
            await asyncio.wait_for(reader.read(),1)
            writer.close()
            await writer.wait_closed()
        with pytest.raises((asyncssh.Error,OSError)):
            await conn.open_connection('192.0.2.1',80,encoding=None)
        await asyncio.wait_for(conn.wait_closed(),1)
    await asyncio.sleep(0.05)
    rows=records(settings)
    assert len([e for e in rows if e['kind']=='forward_open'])==8
    assert len([e for e in rows if e['kind']=='forward_close'])==8
    assert any(e['kind']=='limit' and e['data']['limit']=='forward_channels' for e in rows)


async def test_forward_channel_timeout_releases_capacity(sensor):
    server,settings=sensor
    async with asyncssh.connect('127.0.0.1',server.get_port(),username='root',password='test',known_hosts=None) as conn:
        reader,writer=await conn.open_connection('192.0.2.1',25,encoding=None)
        assert await asyncio.wait_for(reader.read(),11)==b''
        writer.close()
        await writer.wait_closed()
    await asyncio.sleep(0.05)
    assert next(e for e in records(settings) if e['kind']=='forward_close')['data']['reason']=='timeout'


@pytest.mark.parametrize('host,port',[('',80),('x'*1025,80),('192.0.2.1',65536)])
async def test_invalid_forward_destinations_rejected(sensor,host,port):
    server,_=sensor
    async with asyncssh.connect('127.0.0.1',server.get_port(),username='root',password='test',known_hosts=None) as conn:
        with pytest.raises(asyncssh.ChannelOpenError):
            await conn.open_connection(host,port,encoding=None)


async def test_forward_disconnect_records_preview_and_cleans_channels(sensor):
    server,settings=sensor
    conn=await asyncssh.connect('127.0.0.1',server.get_port(),username='root',password='test',known_hosts=None)
    reader,writer=await conn.open_connection('probe.invalid',443,encoding=None)
    writer.write(b'partial payload')
    await writer.drain()
    await asyncio.sleep(0.05)
    conn.abort()
    await conn.wait_closed()
    await asyncio.sleep(0.05)
    closes=[e for e in records(settings) if e['kind']=='forward_close']
    assert len(closes)==1
    assert base64.b64decode(closes[0]['data']['sample_base64'])==b'partial payload'
    assert not server.live_connections


async def test_rejected_forward_request_flood_has_admission_budget(sensor):
    server,settings=sensor
    async with asyncssh.connect('127.0.0.1',server.get_port(),username='root',password='test',known_hosts=None) as conn:
        for _ in range(32):
            with pytest.raises(asyncssh.ChannelOpenError):
                await conn.open_connection('',80,encoding=None)
        with pytest.raises((asyncssh.Error,OSError)):
            await conn.open_connection('',80,encoding=None)
        await asyncio.wait_for(conn.wait_closed(),1)
    await asyncio.sleep(0.05)
    rows=records(settings)
    assert not any(e['kind']=='forward_open' for e in rows)
    assert any(e['kind']=='limit' and e['data']['limit']=='forward_requests' for e in rows)
