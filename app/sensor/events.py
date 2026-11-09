"""Single-process bounded append-only event spool; never logs credentials to stderr."""
import json
import logging
import os
import time
from uuid import uuid4

from app.common.schemas import MAX_EVENT_BYTES, utcnow

log = logging.getLogger(__name__)


class EventWriter:
    def __init__(self, directory, rotate_bytes=4 * 1024**2,
                 max_bytes=256 * 1024**2, retention_days=30):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.rotate_bytes = rotate_bytes
        self.max_bytes = max_bytes
        self.retention_days = retention_days
        self.active = None
        self.active_date = None
        self.healthy = True
        self.maintain()

    def maintain(self, incoming=0):
        cutoff = time.time() - self.retention_days * 86400
        files = sorted(self.directory.glob('*.jsonl'), key=lambda p: p.name)
        sizes = []
        for path in files:
            stat = path.stat()
            if stat.st_mtime < cutoff:
                path.unlink()
                if path == self.active:
                    self.active = None
            else:
                sizes.append((path, stat.st_size))
        total = sum(size for _, size in sizes)
        for path, size in sizes:
            if total + incoming <= self.max_bytes:
                break
            if path != self.active:
                path.unlink()
                total -= size
        if total + incoming > self.max_bytes:
            raise OSError('Event spool capacity exhausted')

    def emit(self, kind, session_id, ip, **data):
        event = {'v': 1, 'id': str(uuid4()), 'ts': utcnow(), 'kind': kind,
                 'session_id': session_id, 'ip': ip,
                 'data': {k: v[:4096] if isinstance(v, str) else v for k, v in data.items()}}
        raw = (json.dumps(event, ensure_ascii=True, allow_nan=False) + '\n').encode()
        try:
            if len(raw) > MAX_EVENT_BYTES or len(raw) > self.max_bytes:
                raise ValueError('Event exceeds size bound')
            self.maintain()
            if self.active is None or self.active_date != event['ts'][:10] or not self.active.exists() or self.active.stat().st_size + len(raw) > self.rotate_bytes:
                self.active = None
                self.maintain(len(raw))
                self.active = self.directory / f'{time.time_ns():020d}-{uuid4().hex}.jsonl'
                self.active_date = event['ts'][:10]
            else:
                self.maintain(len(raw))
            fd = os.open(self.active, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
            try:
                written = os.write(fd, raw)
                if written != len(raw):
                    raise OSError('Partial event write')
            finally:
                os.close(fd)
            self.healthy = True
        except (OSError, ValueError):
            # Never append a valid record to a possibly incomplete failed write.
            self.active = None
            self.healthy = False
            log.error('Event storage failure; event dropped', exc_info=False)
        return event
