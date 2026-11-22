"""Storage limits remain bounded while supporting a four-GiB event budget."""
import pytest

from app.common.config import Settings
from app.web.database import Database

GIB = 1024**3
MAX_EVENTS = 4 * GIB // 1024


def test_four_gib_event_budget_can_be_loaded_from_environment(monkeypatch):
    monkeypatch.setenv('SENTINEL_MAX_EVENT_STORAGE_BYTES', str(4 * GIB))
    monkeypatch.setenv('SENTINEL_MAX_DB_BYTES', str(8 * GIB))
    monkeypatch.setenv('SENTINEL_MAX_DB_EVENTS', str(MAX_EVENTS))
    settings = Settings.from_env()
    assert settings.max_event_storage_bytes == 4294967296
    assert settings.max_db_bytes == 8589934592
    assert settings.max_db_events == 4194304


@pytest.mark.parametrize('overrides,field', [
    ({'max_event_storage_bytes': 4 * GIB + 1, 'max_db_bytes': 8 * GIB}, 'max_event_storage_bytes'),
    ({'max_db_bytes': 8 * GIB + 1}, 'max_db_bytes'),
    ({'max_db_events': MAX_EVENTS + 1}, 'max_db_events'),
])
def test_storage_settings_reject_values_above_supported_maximum(overrides, field):
    with pytest.raises(ValueError, match=field):
        Settings(**overrides)


def test_four_gib_data_budget_still_requires_database_headroom():
    with pytest.raises(ValueError, match='twice max_event_storage_bytes'):
        Settings(max_event_storage_bytes=4 * GIB, max_db_bytes=4 * GIB)


def test_storage_defaults_are_unchanged():
    settings = Settings()
    assert settings.max_event_storage_bytes == 64 * 1024**2
    assert settings.max_db_bytes == 256 * 1024**2
    assert settings.max_db_events == 100000


def test_eight_gib_sqlite_limit_does_not_preallocate_disk_space(tmp_path):
    settings = Settings(max_event_storage_bytes=4 * GIB, max_db_bytes=8 * GIB)
    db = Database(tmp_path / 'large-limit.sqlite', settings.max_db_bytes)
    with db.connect() as conn:
        page_size = conn.execute('PRAGMA page_size').fetchone()[0]
        max_pages = conn.execute('PRAGMA max_page_count').fetchone()[0]
    assert max_pages * page_size == 8 * GIB
    assert db.path.stat().st_size < 1024**2
