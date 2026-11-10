"""Private dashboard database. Sensor never imports this module."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path, max_bytes=256 * 1024**2):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        with self.connect() as conn:
            conn.executescript('''
                PRAGMA journal_mode=WAL;
                PRAGMA auto_vacuum=INCREMENTAL;
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, ts TEXT NOT NULL, kind TEXT NOT NULL,
                    session_id TEXT NOT NULL, ip TEXT NOT NULL, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
                CREATE INDEX IF NOT EXISTS events_session ON events(session_id, ts);
                CREATE INDEX IF NOT EXISTS events_kind ON events(kind, ts);
                CREATE INDEX IF NOT EXISTS events_ip ON events(ip, ts);
                CREATE TABLE IF NOT EXISTS checkpoints (
                    path TEXT PRIMARY KEY, identity TEXT NOT NULL,
                    offset INTEGER NOT NULL, skipping INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS admin (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    username TEXT NOT NULL, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS login_limits (
                    ip TEXT PRIMARY KEY, attempts INTEGER NOT NULL, reset INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS event_usage (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), rows INTEGER NOT NULL, bytes INTEGER NOT NULL);
                INSERT OR IGNORE INTO event_usage
                    SELECT 1, count(*), coalesce(sum(1024+length(data)),0) FROM events;
                CREATE TRIGGER IF NOT EXISTS event_added AFTER INSERT ON events BEGIN
                    UPDATE event_usage SET rows=rows+1, bytes=bytes+1024+length(new.data) WHERE singleton=1;
                END;
                CREATE TRIGGER IF NOT EXISTS event_removed AFTER DELETE ON events BEGIN
                    UPDATE event_usage SET rows=rows-1, bytes=bytes-1024-length(old.data) WHERE singleton=1;
                END;
                CREATE TRIGGER IF NOT EXISTS event_changed AFTER UPDATE OF data ON events BEGIN
                    UPDATE event_usage SET bytes=bytes+length(new.data)-length(old.data) WHERE singleton=1;
                END;
            ''')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        os.chmod(self.path, 0o600)
        conn.row_factory = sqlite3.Row
        page_size = conn.execute('PRAGMA page_size').fetchone()[0]
        conn.execute(f'PRAGMA max_page_count={self.max_bytes // page_size}')
        conn.execute('PRAGMA journal_size_limit=8388608')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def decode(row):
        return {'v': 1, 'id': row['id'], 'ts': row['ts'], 'kind': row['kind'],
                'session_id': row['session_id'], 'ip': row['ip'], 'data': json.loads(row['data'])}

    @staticmethod
    def filters(ip='', username='', kind='', session_id='', since=''):
        where, params = [], []
        for column, value in [('ip', ip), ('kind', kind), ('session_id', session_id)]:
            if value:
                where.append(column + ' = ?')
                params.append(value)
        if username:
            where.append("json_extract(data, '$.username') = ?")
            params.append(username)
        if since:
            where.append('ts >= ?')
            params.append(since)
        return (' WHERE ' + ' AND '.join(where) if where else ''), params

    def events(self, *, ip='', username='', kind='', session_id='', since='', limit=100, offset=0):
        where, params = self.filters(ip, username, kind, session_id, since)
        with self.connect() as conn:
            rows = conn.execute('SELECT * FROM events' + where + ' ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?',
                                [*params, min(max(limit, 1), 1000), max(0, offset)]).fetchall()
        return [self.decode(row) for row in rows]

    def session_summaries(self, *, ip='', username='', kind='', session_id='', limit=50, offset=0):
        """Filter whole SSH sessions, then paginate; retain all their event counts."""
        having, params = [], []
        for expression, value in [('ip', ip), ("json_extract(data, '$.username')", username), ('kind', kind)]:
            if value:
                having.append(f'MAX({expression} = ?) = 1')
                params.append(value)
        where = ' WHERE session_id = ?' if session_id else ''
        values = ([session_id] if session_id else []) + params
        match = ' HAVING ' + ' AND '.join(having) if having else ''
        query = """
            WITH grouped AS (
                SELECT session_id, MIN(ts) first_seen, MAX(ts) last_seen, MIN(ip) ip,
                       COUNT(*) event_count, SUM(kind='auth_attempt') attempts,
                       SUM(kind='command') commands, MAX(kind='disconnect') closed,
                       MAX(kind IN ('shell_start','command','shell_end')) shell_opened,
                       MAX((kind='auth_attempt' AND json_extract(data,'$.accepted')=1)
                           OR (kind='disconnect' AND json_extract(data,'$.authenticated')=1)
                           OR kind IN ('shell_start','command','shell_end')) authenticated
                FROM events""" + where + " GROUP BY session_id" + match + """
                ORDER BY last_seen DESC, session_id DESC LIMIT ? OFFSET ?
            )
            SELECT grouped.*, (SELECT json_extract(u.data,'$.username') FROM events u
                WHERE u.session_id=grouped.session_id AND json_type(u.data,'$.username')='text'
                AND json_extract(u.data,'$.username') != ''
                ORDER BY u.ts DESC, u.id DESC LIMIT 1) username
            FROM grouped ORDER BY last_seen DESC, session_id DESC
        """
        with self.connect() as conn:
            rows = conn.execute(query, [*values, min(max(limit, 1), 1000), max(0, offset)]).fetchall()
        return [dict(row) for row in rows]

    def export(self, **filters):
        where, params = self.filters(**filters)
        # Release each read transaction before yielding to a possibly slow HTTP client.
        # Keyset pagination avoids retaining an unbounded WAL snapshot during exports.
        last = None
        while True:
            clause = (' AND ' if where else ' WHERE ') + '(ts, id) < (?, ?)' if last else ''
            values = [*params, *last] if last else params
            with self.connect() as conn:
                rows = conn.execute('SELECT * FROM events' + where + clause + ' ORDER BY ts DESC, id DESC LIMIT 100', values).fetchall()
            if not rows:
                return
            last = (rows[-1]['ts'], rows[-1]['id'])
            for row in rows:
                yield self.decode(row)

    @staticmethod
    def enforce_event_capacity(conn, max_events, max_bytes):
        while True:
            usage = conn.execute('SELECT rows, bytes FROM event_usage WHERE singleton=1').fetchone()
            if usage['rows'] <= max_events and usage['bytes'] <= max_bytes:
                return
            need_rows = max(0, usage['rows'] - max_events)
            need_bytes = max(0, usage['bytes'] - max_bytes)
            victims, freed = [], 0
            for row in conn.execute('SELECT id, 1024+length(data) size FROM events ORDER BY ts ASC, id ASC LIMIT 512'):
                victims.append((row['id'],))
                freed += row['size']
                if len(victims) >= need_rows and freed >= need_bytes:
                    break
            conn.executemany('DELETE FROM events WHERE id=?', victims)
