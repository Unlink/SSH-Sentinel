import csv
import hashlib
import io
import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from app.common.config import Settings
from app.web.main import create_app
from app.web.auth import set_admin
from app.web.ingestion import Importer
from tests.test_ingestion import event


@pytest.fixture
def web(tmp_path):
    settings = Settings(event_dir=tmp_path / 'events', data_dir=tmp_path / 'data')
    settings.event_dir.mkdir()
    app = create_app(settings)
    set_admin(app.state.db, 'admin', 'a-long-test-password')
    with TestClient(app, base_url='http://localhost') as client:
        yield client, app, settings


def login(client, password='a-long-test-password', headers=None):
    page = client.get('/login')
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    return client.post('/login', data={'username': 'admin', 'password': password, 'csrf': csrf}, headers=headers, follow_redirects=False)


def test_same_origin_browser_login_is_accepted(web):
    client, _, _ = web
    assert login(client, headers={'Origin': 'http://localhost'}).status_code == 303


def test_dashboard_and_login_errors_are_english(web):
    client, _, _ = web
    page = client.get('/login')
    assert '<html lang="en">' in page.text
    assert 'Welcome back.' in page.text
    assert 'Username' in page.text and 'Password' in page.text
    failed = login(client, password='wrong-password')
    assert failed.status_code == 401
    assert 'Invalid username or password.' in failed.text
    assert login(client).status_code == 303
    assert 'See what your honeypot caught.' in client.get('/').text
    assert 'Session history' in client.get('/history').text


def test_setup_login_protected_views_and_csrf(web):
    client, app, _ = web
    for url in ('/', '/history', '/api/stats', '/export.json', '/export.csv'):
        assert client.get(url, follow_redirects=False).status_code == 303
    assert client.post('/login', data={'username': 'admin', 'password': 'a-long-test-password'}).status_code == 403
    assert login(client).status_code == 303
    assert client.get('/').status_code == 200
    assert client.get('/api/stats?days=7').json()['connections'] == 0
    assert client.post('/logout').status_code == 403
    cookie = client.cookies.get('sentinel_session')
    assert cookie
    assert 'httponly' in login(client).headers['set-cookie'].lower()
    with app.state.db.connect() as conn:
        conn.execute('DELETE FROM admin')
        conn.execute('DELETE FROM sessions')
    assert client.get('/login').status_code == 503


def test_xss_session_detail_filters_and_csv_formulas(web):
    client, app, settings = web
    hostile = '<script>alert(1)</script>'
    e = event('auth_attempt', username=hostile, password='=HYPERLINK("https://evil")')
    (settings.event_dir / 'one.jsonl').write_text(json.dumps(e) + '\n')
    Importer(app.state.db, settings.event_dir).run()
    login(client)
    page = client.get('/history').text
    assert hostile not in page and '&lt;script&gt;' in page
    detail = client.get('/sessions/' + e['session_id']).text
    assert hostile not in detail and '&lt;script&gt;' in detail
    assert client.get('/api/events', params={'ip': '192.0.2.99'}).json() == []
    assert len(client.get('/api/events', params={'username': hostile}).json()) == 1
    assert client.get('/export.json').json()[0]['data']['password'].startswith('=')
    exported = list(csv.DictReader(io.StringIO(client.get('/export.csv').text)))
    assert exported[0]['password'].startswith("'=")
    assert 'default-src' in client.get('/').headers['content-security-policy']


def test_session_expiry_revocation_and_throttle(web):
    client, app, _ = web
    login(client)
    token = client.cookies.get('sentinel_session')
    with app.state.db.connect() as conn:
        conn.execute('UPDATE sessions SET expires=0')
    assert client.get('/api/stats', follow_redirects=False).status_code == 303
    login(client)
    set_admin(app.state.db, 'admin', 'another-long-password')
    assert client.get('/', follow_redirects=False).status_code == 303
    # Account reset revokes sessions; prior cookie grants no access.
    client.cookies.set('sentinel_session', token)
    assert client.get('/', follow_redirects=False).status_code == 303
    for _ in range(10):
        response = login(client, 'wrong')
    assert response.status_code == 429


def test_oversized_login_and_cross_origin_are_rejected(web):
    client, _, _ = web
    assert client.post('/login', content='x' * 9000,
                       headers={'Content-Type': 'application/x-www-form-urlencoded'}).status_code == 413
    assert client.post('/login', data={}, headers={'Origin': 'https://evil.example'}).status_code == 403


def test_password_reset_cannot_race_session_creation(tmp_path, monkeypatch):
    from contextlib import contextmanager
    import threading
    from app.web.auth import attempt_login, current_session, password_hash
    from app.web.database import Database
    db = Database(tmp_path / 'race.sqlite')
    set_admin(db, 'admin', 'a-long-test-password')
    replacement_hash = password_hash('new-secure-password')
    original = db.connect
    resetting, reset_done = threading.Event(), threading.Event()
    workers = []

    def reset():
        resetting.set()
        with original() as conn:
            conn.execute('UPDATE admin SET password_hash=?', (replacement_hash,))
            conn.execute('DELETE FROM sessions')
        reset_done.set()

    class Connection:
        def __init__(self, conn):
            self.conn = conn
        def execute(self, sql, params=()):
            if sql.startswith('INSERT INTO sessions'):
                worker = threading.Thread(target=reset)
                workers.append(worker)
                worker.start()
                assert resetting.wait(2)
                # Reset commits here only if login failed to lock the recheck/insert transaction.
                reset_done.wait(.5)
            return self.conn.execute(sql, params)

    @contextmanager
    def instrumented():
        with original() as conn:
            yield Connection(conn)

    monkeypatch.setattr(db, 'connect', instrumented)
    status, token, _ = attempt_login(db, '127.0.0.1', 'admin', 'a-long-test-password')
    for worker in workers:
        worker.join(3)
        assert not worker.is_alive()
    assert reset_done.is_set()
    assert status == 'ok'
    assert current_session(db, token) is None


def seed_session_events(app, settings, kinds, session_id=None, **data):
    from uuid import uuid4
    from datetime import datetime, timedelta, timezone
    session_id = session_id or str(uuid4())
    start = datetime.now(timezone.utc) - timedelta(minutes=1)
    rows = []
    for index, kind in enumerate(kinds):
        row = event(kind, **data)
        row['session_id'] = session_id
        row['ts'] = (start + timedelta(seconds=index)).isoformat(timespec='milliseconds')
        rows.append(row)
    with (settings.event_dir/'session-overview.jsonl').open('a') as stream:
        stream.writelines(json.dumps(row)+'\n' for row in rows)
    Importer(app.state.db, settings.event_dir).run()
    return session_id


def test_history_groups_entire_sessions_and_hides_event_payloads(web):
    client, app, settings = web
    sid = seed_session_events(app, settings,
        ['connection','auth_attempt','shell_start','command','command','disconnect'],
        username='root', password='secret-not-in-overview', command='payload-not-in-overview', accepted=True)
    login(client)
    page = client.get('/history').text
    assert page.count(f'href="/sessions/{sid}"') == 1
    assert 'Session history' in page
    assert 'secret-not-in-overview' not in page and 'payload-not-in-overview' not in page
    assert 'Shell opened' in page and 'Closed' in page
    row = app.state.db.session_summaries()[0]
    assert row['event_count'] == 6 and row['attempts'] == 1 and row['commands'] == 2
    assert len(client.get('/api/events').json()) == 6
    assert 'secret-not-in-overview' in client.get('/sessions/'+sid).text
    assert len(client.get('/export.json').json()) == 6


def test_history_filters_match_across_events_and_keep_full_counts(web):
    client, app, settings = web
    from uuid import uuid4
    sid = str(uuid4())
    seed_session_events(app, settings, ['connection'], sid)
    seed_session_events(app, settings, ['auth_attempt'], sid, username='root', accepted=False)
    seed_session_events(app, settings, ['command'], sid, command='whoami')
    seed_session_events(app, settings, ['connection','disconnect'])
    login(client)
    page = client.get('/history', params={'username':'root','kind':'connection'}).text
    assert page.count(f'href="/sessions/{sid}"') == 1
    rows = app.state.db.session_summaries(username='root', kind='connection')
    assert len(rows) == 1 and rows[0]['event_count'] == 3 and rows[0]['commands'] == 1
    assert client.get('/history', params={'ip':'192.0.2.99'}).text.count('No sessions match') == 1
    partial = client.get('/history', params={'username':'root'}, headers={'HX-Request':'true'}).text
    assert '<html' not in partial and f'href="/sessions/{sid}"' in partial


def test_history_paginates_sessions_and_preserves_partial_session(web):
    client, app, settings = web
    for _ in range(51):
        seed_session_events(app, settings, ['connection','disconnect'])
    sid = seed_session_events(app, settings, ['auth_attempt'], username='partial-user', accepted=False)
    login(client)
    first, second = client.get('/history').text, client.get('/history?page=2').text
    ids_first = re.findall(r'href="/sessions/([^"?]+)"', first)
    ids_second = re.findall(r'href="/sessions/([^"?]+)"', second)
    assert len(ids_first) == 50 and len(ids_second) == 2
    assert not set(ids_first) & set(ids_second)
    assert 'Next' in first and 'Next' not in second
    row = app.state.db.session_summaries(session_id=sid)[0]
    assert row['event_count'] == 1 and row['first_seen'] == row['last_seen']
    page = client.get('/history', params={'session_id':sid}).text
    assert 'No disconnect recorded' in page and 'No authentication' in page


def test_virtual_forwarding_is_imported_grouped_and_escaped(web):
    client, app, settings = web
    hostile = '<script>forwarding_payload</script>'
    sid = seed_session_events(app, settings,
        ['connection','auth_attempt','forward_open','forward_close','disconnect'],
        username='admin', accepted=True, destination_host='probe.invalid', destination_port=443,
        simulated=True, sample_text=hostile, sample_base64='c3ludGhldGlj', received_bytes=9)
    login(client)
    page = client.get('/history').text
    assert 'Forwarding simulated' in page and '1 tunnel' in page
    assert hostile not in page
    row = app.state.db.session_summaries(session_id=sid)[0]
    assert row['forwardings'] == 1 and row['event_count'] == 5
    detail = client.get('/sessions/'+sid).text
    assert 'No connection to the requested destination was made.' in detail
    assert hostile not in detail and '&lt;script&gt;forwarding_payload&lt;/script&gt;' in detail
    assert 'probe.invalid:443' in detail
    assert sid in client.get('/history',params={'kind':'forward_open'}).text
    exported = client.get('/export.json',params={'session_id':sid}).json()
    assert len(exported) == 5 and any(e['kind']=='forward_close' for e in exported)


def test_geoip_flags_and_asn_on_all_ip_views_without_changing_export(web):
    from types import SimpleNamespace
    client,app,settings=web
    sid=seed_session_events(app,settings,['connection','auth_attempt','disconnect'],username='admin',accepted=True)
    info={'country_code':'SK','country_name':'Slovakia','asn':64500,
          'asn_name':'<script>ASN operator</script>','status':'found'}
    app.state.geoip=SimpleNamespace(lookup=lambda ip:info,release='2026-11',available=True)
    login(client)
    for url in ('/','/history','/sessions/'+sid):
        page=client.get(url).text
        assert '/static/flags/sk.svg' in page
        assert 'Slovakia' in page and 'AS64500' in page
        assert '<script>ASN operator</script>' not in page
        assert '&lt;script&gt;ASN operator&lt;/script&gt;' in page
        assert 'https://db-ip.com' in page
    partial=client.get('/history',headers={'HX-Request':'true'}).text
    assert '/static/flags/sk.svg' in partial and 'AS64500' in partial
    exported=client.get('/export.json',params={'session_id':sid}).json()
    assert all(set(e)=={'v','id','ts','kind','session_id','ip','data'} for e in exported)
    assert all('country_code' not in e['data'] for e in exported)
