import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.web.database import Database
from app.web.ingestion import Importer
from app.web.analytics import summary


def event(kind='connection', **data):
    return {'v': 1, 'id': str(uuid4()), 'ts': datetime.now(timezone.utc).isoformat(),
            'kind': kind, 'session_id': str(uuid4()), 'ip': '192.0.2.1', 'data': data}


def test_restart_partial_and_duplicate_import(tmp_path):
    db = Database(tmp_path / 'db.sqlite')
    spool = tmp_path / 'events'
    spool.mkdir()
    first, second = event(), event('auth_attempt', username='root', password='secret')
    path = spool / 'events.jsonl'
    raw = json.dumps(second)
    path.write_text(json.dumps(first) + '\n' + raw[:70])
    assert Importer(db, spool, 30).run() == 1
    assert Importer(db, spool, 30).run() == 0
    with path.open('a') as f:
        f.write(raw[70:] + '\n' + json.dumps(first) + '\n')
    assert Importer(db, spool, 30).run() == 1
    assert len(db.events()) == 2
    assert db.events(kind='auth_attempt')[0]['data']['password'] == 'secret'


def test_malformed_oversized_replaced_and_expired(tmp_path):
    db = Database(tmp_path / 'db.sqlite')
    spool = tmp_path / 'events'
    spool.mkdir()
    path = spool / 'events.jsonl'
    old = event()
    old['ts'] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    fresh = event()
    path.write_text('not-json\n' + 'x' * 100000 + '\n' + json.dumps(old) + '\n' + json.dumps(fresh) + '\n')
    importer = Importer(db, spool, 30)
    assert importer.run() == 1
    assert len(db.events()) == 1
    replacement = event('command', command='ls')
    path.unlink()
    path.write_text(json.dumps(replacement) + '\n')
    assert importer.run() == 1
    assert len(db.events()) == 2
    # A replay of an old log cannot repopulate expired data.
    path.write_text(json.dumps(old) + '\n')
    assert importer.run() == 0
    assert len(db.events()) == 2


def test_retention_filters_and_aggregates(tmp_path):
    db = Database(tmp_path / 'db.sqlite')
    spool = tmp_path / 'events'
    spool.mkdir()
    entries = [event(), event('auth_attempt', username='root', password='test'),
               event('shell_start'), event('command', command='ls'),
               event('disconnect', authenticated=False)]
    (spool / 'one.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in entries))
    Importer(db, spool, 30).run()
    stats = summary(db, 1)
    assert stats['connections'] == 1
    assert stats['attempts'] == 1
    assert stats['shells'] == 1
    assert stats['unique_ips'] == 1
    assert stats['unauthenticated'] == 1
    assert len(stats['activity']) == 24
    assert sum(bucket['connections'] for bucket in stats['activity']) == 1
    assert stats['top_users'][0] == {'label': 'root', 'count': 1}
    assert len(db.events(ip='192.0.2.1', username='root')) == 1
    assert not db.events(ip="' OR 1=1--")
    with db.connect() as conn:
        conn.execute("UPDATE events SET ts='2000-01-01T00:00:00.000+00:00'")
    Importer(db, spool, 30).run()
    assert db.events() == []


def test_untrusted_schema_and_future_time_are_rejected(tmp_path):
    db = Database(tmp_path / 'db.sqlite')
    spool = tmp_path / 'events'
    spool.mkdir()
    invalid = [event(), event(), event(), event()]
    invalid[0]['ip'] = '<script>alert(1)</script>'
    invalid[1]['data'] = {'command': {'nested': 'object'}}
    invalid[2]['ts'] = '2999-01-01T00:00:00+00:00'
    invalid[3]['id'] = 123
    (spool / 'bad.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in invalid))
    assert Importer(db, spool, 30).run() == 0


def test_symlink_spool_is_not_imported(tmp_path):
    import os
    import pytest
    db = Database(tmp_path / 'db.sqlite')
    spool = tmp_path / 'events'
    spool.mkdir()
    outside = tmp_path / 'secret.jsonl'
    outside.write_text(json.dumps(event()) + '\n')
    try:
        os.symlink(outside, spool / 'link.jsonl')
    except OSError:
        pytest.skip('OS does not permit symlink creation')
    assert Importer(db, spool, 30).run() == 0


def test_event_capacity_preserves_newest_and_does_not_replay_pruned(tmp_path):
    db = Database(tmp_path / 'db.sqlite')
    spool = tmp_path / 'events'
    spool.mkdir()
    entries = [event(command=str(i)) for i in range(12)]
    for i, entry in enumerate(entries):
        entry['ts'] = (datetime.now(timezone.utc) - timedelta(seconds=20-i)).isoformat()
    (spool / 'all.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in entries))
    importer = Importer(db, spool, 30, max_events=5)
    importer.run()
    assert len(db.events()) == 5
    assert {e['id'] for e in db.events()} == {e['id'] for e in entries[-5:]}
    assert importer.run() == 0
    assert len(db.events()) == 5


def test_spool_filename_count_is_bounded_and_recovers(tmp_path):
    import pytest
    db = Database(tmp_path / 'db.sqlite')
    spool = tmp_path / 'events'
    spool.mkdir()
    for i in range(6):
        (spool / f'{i}.jsonl').touch()
    importer = Importer(db, spool, max_files=5)
    with pytest.raises(ValueError, match='file count'):
        importer.run()
    (spool / '0.jsonl').unlink()
    (spool / '1.jsonl').write_text(json.dumps(event()) + '\n')
    assert importer.run() == 1


def test_one_unreadable_file_does_not_block_other_records(tmp_path, monkeypatch):
    import os
    import app.web.ingestion as ingestion
    db = Database(tmp_path / 'db.sqlite')
    spool = tmp_path / 'events'
    spool.mkdir()
    bad = spool / '0-bad.jsonl'
    bad.write_text(json.dumps(event()) + '\n')
    (spool / '1-good.jsonl').write_text(json.dumps(event()) + '\n')
    original = os.open
    def deny(path, flags, *args, **kwargs):
        if path == bad:
            raise PermissionError('unreadable spool file')
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(ingestion.os, 'open', deny)
    assert Importer(db, spool).run() == 1
