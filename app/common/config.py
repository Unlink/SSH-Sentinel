"""Validated shared settings. No secrets are passed to the sensor."""
import os
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    event_dir: Path = Path('/events')
    data_dir: Path = Path('/data')
    key_dir: Path = Path('/keys')
    geoip_path: Path = Path(__file__).resolve().parents[2] / 'geoip.sqlite'
    ssh_host: str = '0.0.0.0'
    ssh_port: int = 2222
    proxy_protocol: bool = False
    log_passwords: bool = True
    max_connections: int = 64
    max_line: int = 4096
    max_commands: int = 200
    session_seconds: int = 300
    login_seconds: int = 20
    retention_days: int = 30
    rotate_bytes: int = 4 * 1024 * 1024
    spool_bytes: int = 256 * 1024 * 1024
    import_seconds: int = 5
    cookie_secure: bool = False
    allowed_hosts: str = 'localhost,127.0.0.1'
    max_db_events: int = 100000
    max_event_storage_bytes: int = 64 * 1024**2
    max_db_bytes: int = 256 * 1024**2
    max_spool_files: int = 4096

    def __post_init__(self):
        for name in ('event_dir', 'data_dir', 'key_dir', 'geoip_path'):
            object.__setattr__(self, name, Path(getattr(self, name)))
        limits = {'ssh_port': (0, 65535), 'max_connections': (1, 1024),
                  'max_line': (64, 4096), 'max_commands': (1, 10000),
                  'session_seconds': (1, 3600), 'login_seconds': (1, 120),
                  'retention_days': (1, 3650), 'rotate_bytes': (1024, 64 * 1024 * 1024),
                  'spool_bytes': (65536, 10 * 1024**3), 'import_seconds': (1, 300),
                  'max_db_events': (100, 1000000), 'max_event_storage_bytes': (1048576, 1024**3),
                  'max_db_bytes': (16 * 1024**2, 4 * 1024**3), 'max_spool_files': (32, 16384)}
        for name, (low, high) in limits.items():
            if not low <= getattr(self, name) <= high:
                raise ValueError(f'{name} must be between {low} and {high}')
        if self.spool_bytes < self.rotate_bytes:
            raise ValueError('spool_bytes must be >= rotate_bytes')
        if self.max_db_bytes < self.max_event_storage_bytes * 2:
            raise ValueError('max_db_bytes must be >= twice max_event_storage_bytes')

    @classmethod
    def from_env(cls):
        defaults = cls()
        values = {}
        for field in fields(cls):
            raw = os.getenv('SENTINEL_' + field.name.upper())
            if raw is None:
                continue
            default = getattr(defaults, field.name)
            if isinstance(default, bool):
                if raw.lower() not in ('true', 'false', '1', '0'):
                    raise ValueError(f'{field.name} must be true/false')
                values[field.name] = raw.lower() in ('true', '1')
            else:
                values[field.name] = type(default)(raw)
        return cls(**values)
