"""Bounded, restart-safe JSONL import with atomic event/checkpoint commits."""
import hashlib
import json
import logging
import os
import shutil
import stat as stat_module
from datetime import datetime, timedelta, timezone

from app.common.schemas import MAX_EVENT_BYTES, validate_event


class Importer:
    def __init__(self, db, event_dir, retention_days=30, max_events=100000,
                 max_event_bytes=64 * 1024**2, max_files=4096):
        self.db, self.event_dir, self.retention_days = db, event_dir, retention_days
        self.max_events, self.max_event_bytes, self.max_files = max_events, max_event_bytes, max_files
        self.had_errors = False

    def run(self):
        if shutil.disk_usage(self.db.path.parent).free < 64 * 1024**2:
            raise OSError('Less than 64 MiB free disk space; import suspended')
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=self.retention_days)).isoformat(timespec='milliseconds')
        future = (now + timedelta(minutes=5)).isoformat(timespec='milliseconds')
        imported = 0
        budget = 8 * 1024**2
        self.had_errors = False
        paths = []
        with os.scandir(self.event_dir) as entries:
            for count, entry in enumerate(entries, 1):
                if count > self.max_files:
                    raise ValueError('Spool file count exceeds configured limit')
                if entry.name.endswith('.jsonl'):
                    paths.append(self.event_dir / entry.name)
        paths.sort()
        with self.db.connect() as conn:
            conn.execute('DELETE FROM events WHERE ts < ?', (cutoff,))
            present = {path.name for path in paths}
            for row in conn.execute('SELECT path FROM checkpoints'):
                if row['path'] not in present:
                    conn.execute('DELETE FROM checkpoints WHERE path=?', (row['path'],))
            for path in paths:
                if budget <= 0:
                    break
                # Spool is a trust boundary: never follow a sensor-created symlink.
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
                    with os.fdopen(fd, 'rb') as stream:
                        stat = os.fstat(stream.fileno())
                        if not stat_module.S_ISREG(stat.st_mode):
                            continue
                        identity = f'{stat.st_dev}:{stat.st_ino}:' + hashlib.sha256(stream.read(256)).hexdigest()
                        checkpoint = conn.execute('SELECT * FROM checkpoints WHERE path=?', (path.name,)).fetchone()
                        offset, skipping = 0, False
                        if checkpoint and checkpoint['identity'] == identity and checkpoint['offset'] <= stat.st_size:
                            offset, skipping = checkpoint['offset'], bool(checkpoint['skipping'])
                        stream.seek(offset)
                        while budget > 0:
                            start = stream.tell()
                            line = stream.readline(MAX_EVENT_BYTES + 1)
                            budget -= len(line)
                            if not line:
                                break
                            if skipping:
                                skipping = not line.endswith(b'\n')
                                offset = stream.tell()
                                continue
                            if len(line) > MAX_EVENT_BYTES:
                                skipping = not line.endswith(b'\n')
                                offset = stream.tell()
                                logging.warning('Skipped oversized spool record')
                                continue
                            if not line.endswith(b'\n'):
                                offset = start
                                break
                            offset = stream.tell()
                            try:
                                event = validate_event(json.loads(line))
                                if not cutoff <= event['ts'] <= future:
                                    continue
                                cursor = conn.execute('INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?)',
                                    (event['id'], event['ts'], event['kind'], event['session_id'],
                                     event['ip'], json.dumps(event['data'], ensure_ascii=True, allow_nan=False)))
                                imported += cursor.rowcount
                                if imported and imported % 128 == 0:
                                    self.db.enforce_event_capacity(conn, self.max_events, self.max_event_bytes)
                            except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
                                logging.warning('Skipped invalid spool record')
                        conn.execute('INSERT OR REPLACE INTO checkpoints VALUES (?, ?, ?, ?)',
                                     (path.name, identity, offset, int(skipping)))
                except FileNotFoundError:
                    continue  # Sensor can rotate/delete while the importer is scanning.
                except OSError:
                    self.had_errors = True
                    logging.warning('Unreadable spool file skipped')
            self.db.enforce_event_capacity(conn, self.max_events, self.max_event_bytes)
            conn.execute('DELETE FROM sessions WHERE expires < ?', (int(now.timestamp()),))
            conn.execute('DELETE FROM login_limits WHERE reset < ?', (int(now.timestamp()),))
            conn.execute('PRAGMA incremental_vacuum(128)')
        return imported
