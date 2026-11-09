"""Simulated authentication only. Never checks host accounts."""


def authenticate(writer, settings, session_id, ip, username, password):
    accepted = bool(username) and len(username) <= 256 and len(password) <= 4096
    data = {'username': username, 'accepted': accepted, 'method': 'password'}
    if settings.log_passwords:
        data['password'] = password
    writer.emit('auth_attempt', session_id, ip, **data)
    return accepted
