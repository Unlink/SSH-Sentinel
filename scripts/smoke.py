"""Optional localhost Compose smoke test. Refuses to replace an existing admin."""
import asyncio
import http.cookiejar
import json
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

import asyncssh


def compose(*args, input=None):
    result = subprocess.run(['docker', 'compose', *args], input=input, text=True,
                            capture_output=True, check=True)
    return result.stdout.strip()


async def ssh_probe():
    async with asyncssh.connect('127.0.0.1', 2222, username='smoke-probe',
                                password='local-smoke-password', known_hosts=None) as conn:
        assert (await conn.run('whoami')).stdout == 'smoke-probe\n'


def main():
    password = secrets.token_urlsafe(32)
    bootstrap = """
import sys
from app.web.database import Database
from app.web.auth import set_admin
db=Database('/data/sentinel.sqlite')
with db.connect() as c:
    assert not c.execute('SELECT 1 FROM admin').fetchone(), 'Existing admin: smoke test refuses to replace it'
set_admin(db, '__smoke__', sys.stdin.read())
"""
    compose('exec', '-T', 'web', 'python', '-c', bootstrap, input=password)
    try:
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        page = client.open('http://127.0.0.1:8080/login').read().decode()
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        body = urllib.parse.urlencode({'username': '__smoke__', 'password': password, 'csrf': csrf}).encode()
        response = client.open('http://127.0.0.1:8080/login', body)
        assert response.status == 200 and 'See what your honeypot caught.' in response.read().decode()
        for asset in ('app.css', 'dashboard.js', 'vendor/htmx.min.js', 'vendor/chart.umd.js'):
            assert client.open('http://127.0.0.1:8080/static/' + asset).status == 200
        asyncio.run(ssh_probe())
        snapshot = []
        for _ in range(20):
            snapshot = json.load(client.open('http://127.0.0.1:8080/export.json?username=smoke-probe'))
            if any(e['kind'] == 'auth_attempt' for e in snapshot):
                break
            time.sleep(.5)
        assert any(e['data'].get('password') == 'local-smoke-password' for e in snapshot)
        ids = {e['id'] for e in snapshot}
        compose('restart')
        for _ in range(40):
            try:
                after = json.load(client.open('http://127.0.0.1:8080/export.json?username=smoke-probe', timeout=2))
                if ids <= {e['id'] for e in after}:
                    break
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(.5)
        else:
            raise AssertionError('Data/session not preserved across restart')
        assert len(after) == len({e['id'] for e in after})
        check = """
import os
from pathlib import Path
assert os.getuid()==10001
status=Path('/proc/self/status').read_text()
assert 'CapEff:\\t0000000000000000' in status and 'NoNewPrivs:\\t1' in status
try:
    Path('/opt/sentinel/write-probe').write_text('probe')
except OSError:
    pass
else:
    raise AssertionError('Root filesystem is writable')
"""
        compose('exec', '-T', 'sensor', 'python', '-c', check + "\nassert not Path('/data').exists()\nassert not Path('/opt/sentinel/app/web').exists()")
        compose('exec', '-T', 'web', 'python', '-c', check + """
try:
    Path('/events/write-probe').write_text('probe')
except OSError:
    pass
else:
    raise AssertionError('Web can write to event spool')
""")
        print('PASS: login, assets, SSH/password capture, import, restart persistence and container hardening')
    finally:
        compose('exec', '-T', 'web', 'python', '-c', "from app.web.database import Database; db=Database('/data/sentinel.sqlite');\nwith db.connect() as c:\n c.execute(\"DELETE FROM admin WHERE username='__smoke__'\"); c.execute('DELETE FROM sessions')")


if __name__ == '__main__':
    main()
