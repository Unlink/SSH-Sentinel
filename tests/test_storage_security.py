import json
import sqlite3

import pytest

from app.web.database import Database
from app.web.ingestion import Importer
from tests.test_ingestion import event


def test_payload_quota_and_usage_counters(tmp_path):
    db = Database(tmp_path / 'db.sqlite')
    spool = tmp_path / 'events'
    spool.mkdir()
    entries = [event('command', command='X' * 500) for _ in range(20)]
    (spool / 'all.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in entries))
    Importer(db, spool, max_events=100, max_event_bytes=4000).run()
    assert 0 < len(db.events()) <= 2
    with db.connect() as conn:
        usage = conn.execute('SELECT rows, bytes FROM event_usage').fetchone()
        assert usage['rows'] == len(db.events())
        assert usage['bytes'] <= 4000


def test_sqlite_page_budget_rejects_oversized_write(tmp_path):
    db = Database(tmp_path / 'db.sqlite', max_bytes=1024**2)
    e = event('command')
    with pytest.raises(sqlite3.DatabaseError, match='full'):
        with db.connect() as conn:
            conn.execute('INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)',
                         (e['id'], e['ts'], e['kind'], e['session_id'], e['ip'], 'x' * (2 * 1024**2)))
    assert db.events() == []


def test_slow_export_does_not_pin_wal(tmp_path):
    db = Database(tmp_path / 'db.sqlite')
    spool = tmp_path / 'events'
    spool.mkdir()
    entries = [event() for _ in range(150)]
    (spool / 'all.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in entries))
    Importer(db, spool).run()
    export = db.export()
    first = next(export)
    try:
        with db.connect() as conn:
            conn.execute('PRAGMA busy_timeout=0')
            assert conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0
        remainder = list(export)
        assert len({e['id'] for e in [first, *remainder]}) == 150
    finally:
        export.close()
