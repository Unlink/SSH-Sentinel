import json
import os
import time

from app.sensor.events import EventWriter


def test_writer_bounds_rotates_and_expires(tmp_path):
    writer = EventWriter(tmp_path, rotate_bytes=1000, max_bytes=4000, retention_days=30)
    for _ in range(30):
        writer.emit('command', 'session', '127.0.0.1', command='x' * 200)
    files = list(tmp_path.glob('*.jsonl'))
    assert 1 < len(files) < 30
    assert sum(f.stat().st_size for f in files) <= 4000
    records = [json.loads(line) for f in files for line in f.read_text().splitlines()]
    assert len({r['id'] for r in records}) == len(records)
    old = tmp_path / 'old.jsonl'
    old.write_text('{}\n')
    os.utime(old, (time.time() - 31 * 86400,) * 2)
    writer.maintain()
    assert not old.exists()


def test_writer_truncates_untrusted_fields(tmp_path):
    writer = EventWriter(tmp_path)
    event = writer.emit('auth_attempt', 'session', '127.0.0.1', username='x' * 10000, password='secret')
    assert len(event['data']['username']) <= 4096
    assert event['data']['password'] == 'secret'


def test_partial_write_does_not_poison_next_event(tmp_path, monkeypatch):
    real_write = os.write
    def partial(fd, data):
        return real_write(fd, data[:len(data) // 2])
    writer = EventWriter(tmp_path)
    monkeypatch.setattr(os, 'write', partial)
    writer.emit('connection', 'session', '127.0.0.1')
    assert not writer.healthy
    monkeypatch.setattr(os, 'write', real_write)
    expected = writer.emit('connection', 'session', '127.0.0.1')
    complete = []
    for path in tmp_path.glob('*.jsonl'):
        for line in path.read_text().splitlines(keepends=True):
            if line.endswith('\n'):
                complete.append(json.loads(line))
    assert any(e['id'] == expected['id'] for e in complete)


def test_daily_rotation_prevents_indefinite_low_traffic_retention(tmp_path, monkeypatch):
    import app.sensor.events as module
    monkeypatch.setattr(module, 'utcnow', lambda: '2026-11-07T00:00:00.000+00:00')
    writer = EventWriter(tmp_path)
    writer.emit('connection', 'session', '127.0.0.1')
    first = writer.active
    monkeypatch.setattr(module, 'utcnow', lambda: '2026-11-08T00:00:00.000+00:00')
    writer.emit('connection', 'session', '127.0.0.1')
    assert writer.active != first
