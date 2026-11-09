"""Single admin, scrypt hashes, opaque revocable sessions and bounded login attempts."""
import hashlib
import hmac
import secrets
import time


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=1,
                            maxmem=64 * 1024**2).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password, encoded):
    try:
        method, salt, _ = encoded.split('$')
        return method == 'scrypt' and hmac.compare_digest(password_hash(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def set_admin(db, username, password):
    if not username.strip() or len(username) > 128:
        raise ValueError('Username must contain 1–128 characters')
    if not 12 <= len(password) <= 1024:
        raise ValueError('Password must contain 12–1024 characters')
    hashed = password_hash(password)
    with db.connect() as conn:
        conn.execute('INSERT OR REPLACE INTO admin VALUES (1, ?, ?)', (username, hashed))
        conn.execute('DELETE FROM sessions')
        conn.execute('DELETE FROM login_limits')


def current_session(db, token):
    if not token or len(token) > 128:
        return None
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>?',
                           (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
    return dict(row) if row else None


def attempt_login(db, ip, username, password):
    now = int(time.time())
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM login_limits WHERE ip=?', (ip,)).fetchone()
        attempts = row['attempts'] if row and row['reset'] > now else 0
        reset = row['reset'] if row and row['reset'] > now else now + 300
        if attempts >= 5:
            return 'limited', None, None
        conn.execute('INSERT OR REPLACE INTO login_limits VALUES (?, ?, ?)', (ip, attempts + 1, reset))
        account = conn.execute('SELECT * FROM admin WHERE singleton=1').fetchone()
    # Always perform a password derivation to avoid a username timing oracle.
    encoded = account['password_hash'] if account else 'scrypt$' + '00' * 16 + '$' + '00' * 64
    valid = verify_password(password, encoded)
    if not account or not hmac.compare_digest(username.encode(), account['username'].encode()) or not valid:
        return 'invalid', None, None
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        # Recheck account in case its password changed during scrypt verification.
        latest = conn.execute('SELECT password_hash FROM admin WHERE singleton=1').fetchone()
        if not latest or latest[0] != encoded:
            return 'invalid', None, None
        conn.execute('INSERT INTO sessions VALUES (?, ?, ?)',
                     (hashlib.sha256(token.encode()).hexdigest(), csrf, now + 8 * 3600))
        conn.execute('DELETE FROM login_limits WHERE ip=?', (ip,))
    return 'ok', token, csrf
