import json
import secrets
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

NAME = 'ssh-sentinel-browser-audit'


def docker(*args, input=None):
    return subprocess.run(['docker', *args], input=input, text=True, capture_output=True, check=True).stdout


def main():
    password = secrets.token_urlsafe(32)
    created = False
    out = Path('docs/audit')
    try:
        docker('run', '-d', '--name', NAME, '--read-only', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '-p', '127.0.0.1:18080:8080',
               '--tmpfs', '/data:uid=10001,gid=10001,mode=0700',
               '--tmpfs', '/events:uid=10001,gid=10001,mode=0750',
               '--tmpfs', '/tmp:size=16m', 'ssh-sentinel-web:local')
        created = True
        seed = '''
import sys,json
from datetime import datetime,timezone
from uuid import uuid4
from app.web.database import Database
from app.web.auth import set_admin
db=Database('/data/sentinel.sqlite')
set_admin(db,'browser-audit',sys.stdin.read())
sid=str(uuid4())
with db.connect() as c:
 for kind,data in [('connection',{}),('auth_attempt',{'username':'attacker<script>window.__xss=1</script>','password':'synthetic-browser-test'}),('shell_start',{}),('command',{'command':'uname -a'})]:
  c.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',(str(uuid4()),datetime.now(timezone.utc).isoformat(),kind,sid,'192.0.2.44',json.dumps(data)))
'''
        docker('exec', '-i', NAME, 'python', '-c', seed, input=password)
        for _ in range(30):
            try:
                urllib.request.urlopen('http://127.0.0.1:18080/healthz', timeout=1)
                break
            except OSError:
                time.sleep(.2)
        errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width':1440,'height':1000})
            page.set_default_timeout(10000)
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
            page.goto('http://127.0.0.1:18080/login')
            page.get_by_label('Username').fill('browser-audit')
            page.get_by_label('Password', exact=True).fill(password)
            with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/login')) as submitted:
                page.get_by_role('button', name='Sign in').click()
            if submitted.value.status >= 400:
                headers = submitted.value.request.all_headers()
                print('LOGIN FAILURE:', submitted.value.status, submitted.value.text()[:120],
                      {k:v for k,v in headers.items() if k in ('origin','host',':authority')}, page.url, errors, flush=True)
                page.screenshot(path=str(out/'browser-login-failure.png'), full_page=True)
            page.wait_for_url('http://127.0.0.1:18080/')
            page.wait_for_function("window.Chart && Chart.getChart(document.getElementById('activity-chart'))?.data.datasets[0].data.some(x=>x>0)")
            assert page.evaluate('htmx.version') == '2.0.11'
            assert page.evaluate('Chart.version') == '4.6.1'
            page.screenshot(path=str(out/'dashboard-desktop.png'), full_page=True)
            page.get_by_role('link', name='Events', exact=True).click()
            page.get_by_label('Source IP').fill('192.0.2.44')
            with page.expect_response(lambda r: '/history?' in r.url and r.request.headers.get('hx-request') == 'true'):
                page.get_by_role('button', name='Filter').click()
            page.wait_for_function("document.querySelector('tbody').innerText.includes('attacker<script>')")
            assert page.evaluate('window.__xss') is None
            # Exercise real HTMX swapping and preserved escaped markup.
            assert page.locator('tbody tr').count() == 4
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(out/'history-mobile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.get_by_role('button', name='Sign out').click()
            page.wait_for_url('**/login')
            assert not errors, errors
            browser.close()
        result = {'browser':'Microsoft Edge headless','htmx':'2.0.11','chartjs':'4.6.1',
                  'login':True,'chart_render':True,'htmx_filter':True,'xss_inert':True,
                  'mobile_no_overflow':True,'logout':True,'console_errors':errors}
        (out/'browser-check.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
    finally:
        if created:
            docker('rm','-f',NAME)


if __name__ == '__main__':
    main()
