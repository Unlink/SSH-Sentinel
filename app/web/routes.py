"""Authenticated HTML, statistics and streaming exports."""
import asyncio
import csv
import hashlib
import hmac
import io
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.web.analytics import summary
from app.web.auth import attempt_login, current_session

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / 'templates')


def require_session(request: Request):
    session = current_session(request.app.state.db, request.cookies.get('sentinel_session'))
    if not session:
        raise HTTPException(303, headers={'Location': '/login'})
    return session


def render(request, name, **context):
    return templates.TemplateResponse(request=request, name=name, context=context)


async def form_data(request):
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > 8192:
            raise HTTPException(413, 'Form too large')
    if not body:
        return {}
    if request.headers.get('content-type', '').split(';')[0] != 'application/x-www-form-urlencoded':
        raise HTTPException(400, 'Expected form encoding')
    try:
        values = parse_qs(body.decode('utf-8'), keep_blank_values=True, max_num_fields=8)
        if any(len(v) != 1 for v in values.values()):
            raise ValueError('Duplicate form field')
        return {key: val[0] for key, val in values.items()}
    except (UnicodeError, ValueError):
        raise HTTPException(400, 'Invalid form') from None


def csrf_check(actual, expected):
    if not actual or not expected or not hmac.compare_digest(actual.encode(), expected.encode()):
        raise HTTPException(403, 'Invalid CSRF token')


@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    with request.app.state.db.connect() as conn:
        ready = conn.execute('SELECT 1 FROM admin').fetchone()
    if not ready:
        response = render(request, 'setup.html', session=None)
        response.status_code = 503
        return response
    csrf = secrets.token_urlsafe(32)
    response = render(request, 'login.html', csrf=csrf, error='', session=None)
    response.set_cookie('sentinel_login_csrf', csrf, max_age=600, httponly=True,
                        secure=request.app.state.settings.cookie_secure, samesite='strict')
    return response


@router.post('/login')
async def login(request: Request):
    form = await form_data(request)
    csrf_check(form.get('csrf'), request.cookies.get('sentinel_login_csrf'))
    username, password = form.get('username', ''), form.get('password', '')
    if len(username) > 128 or len(password) > 1024:
        raise HTTPException(400, 'Credentials too long')
    async with request.app.state.login_slots:
        status, token, _ = await asyncio.to_thread(
            attempt_login, request.app.state.db, request.client.host, username, password)
    if status == 'limited':
        return PlainTextResponse('Too many attempts. Retry in five minutes.', status_code=429, headers={'Retry-After': '300'})
    if status != 'ok':
        response = render(request, 'login.html', csrf=form['csrf'], error='Invalid username or password.', session=None)
        response.status_code = 401
        return response
    response = RedirectResponse('/', status_code=303)
    response.set_cookie('sentinel_session', token, max_age=8 * 3600, httponly=True,
                        secure=request.app.state.settings.cookie_secure, samesite='strict')
    response.delete_cookie('sentinel_login_csrf')
    return response


@router.post('/logout')
async def logout(request: Request, session=Depends(require_session)):
    form = await form_data(request)
    csrf_check(form.get('csrf'), session['csrf'])
    with request.app.state.db.connect() as conn:
        conn.execute('DELETE FROM sessions WHERE token_hash=?', (session['token_hash'],))
    response = RedirectResponse('/login', status_code=303)
    response.delete_cookie('sentinel_session')
    return response


@router.get('/', response_class=HTMLResponse)
def dashboard(request: Request, days: int = 1, session=Depends(require_session)):
    days = days if days in (1, 7, 30) else 1
    return render(request, 'dashboard.html', session=session, days=days,
                  stats=summary(request.app.state.db, days), page='dashboard')


@router.get('/api/stats')
def stats(request: Request, days: int = 1, session=Depends(require_session)):
    return summary(request.app.state.db, days)


def filters(request):
    result = {}
    for name in ('ip', 'username', 'kind', 'session_id'):
        value = request.query_params.get(name, '')
        if len(value) > 4096:
            raise HTTPException(400, 'Filter too long')
        result[name] = value
    return result


@router.get('/history', response_class=HTMLResponse)
def history(request: Request, page: int = 1, session=Depends(require_session)):
    page = max(1, min(page, 10000))
    selected = filters(request)
    sessions = request.app.state.db.session_summaries(**selected, limit=51, offset=(page - 1) * 50)
    context = dict(session=session, sessions=sessions[:50], has_next=len(sessions) > 50,
                   selected=selected, number=page, page='history')
    partial = request.headers.get('HX-Request') == 'true'
    return render(request, 'history_table.html' if partial else 'history.html', **context)


@router.get('/api/events')
def events(request: Request, page: int = 1, session=Depends(require_session)):
    return request.app.state.db.events(**filters(request), limit=100, offset=(max(1, min(page, 10000)) - 1) * 100)


@router.get('/sessions/{session_id}', response_class=HTMLResponse)
def session_detail(request: Request, session_id: UUID, session=Depends(require_session)):
    events = request.app.state.db.events(session_id=str(session_id), limit=1000)
    if not events:
        raise HTTPException(404, 'Session not found')
    return render(request, 'session.html', session=session, events=list(reversed(events)),
                  session_id=session_id, page='history')


def csv_cell(value):
    value = str(value) if value is not None else ''
    if value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


@router.get('/export.{format}')
def export(request: Request, format: str, session=Depends(require_session)):
    if format not in ('json', 'csv'):
        raise HTTPException(404)
    selected = filters(request)

    def stream():
        if format == 'json':
            yield '['
            separator = ''
            for event in request.app.state.db.export(**selected):
                yield separator + json.dumps(event, ensure_ascii=True, allow_nan=False)
                separator = ','
            yield ']'
        else:
            fields = ['ts', 'kind', 'ip', 'session_id', 'username', 'password', 'command', 'data']
            buf = io.StringIO(newline='')
            writer = csv.writer(buf)
            writer.writerow(fields)
            yield buf.getvalue()
            for event in request.app.state.db.export(**selected):
                buf.seek(0)
                buf.truncate()
                data = event['data']
                values = [event['ts'], event['kind'], event['ip'], event['session_id'],
                          data.get('username', ''), data.get('password', ''), data.get('command', ''),
                          json.dumps(data, ensure_ascii=True)]
                writer.writerow([csv_cell(v) for v in values])
                yield buf.getvalue()
    return StreamingResponse(stream(), media_type='application/json' if format == 'json' else 'text/csv',
                             headers={'Content-Disposition': f'attachment; filename="ssh-sentinel.{format}"'})
