"""The only accepted event protocol across the sensor/web trust boundary."""
import ipaddress
from datetime import datetime, timezone
from uuid import UUID

MAX_EVENT_BYTES = 65536
KINDS = {'connection', 'handshake', 'auth_attempt', 'shell_start', 'command',
         'shell_end', 'disconnect', 'limit', 'denied', 'forward_open', 'forward_close'}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def validate_event(event):
    if not isinstance(event, dict) or event.get('v') != 1:
        raise ValueError('invalid event version')
    for field in ('id', 'session_id', 'ip', 'kind', 'ts'):
        if not isinstance(event.get(field), str):
            raise ValueError('invalid event field type')
    UUID(event['id'])
    UUID(event['session_id'])
    ipaddress.ip_address(event['ip'])
    if event['kind'] not in KINDS:
        raise ValueError('invalid kind')
    stamp = datetime.fromisoformat(event['ts'])
    if stamp.tzinfo is None:
        raise ValueError('timezone required')
    event['ts'] = stamp.astimezone(timezone.utc).isoformat(timespec='milliseconds')
    data = event['data']
    if not isinstance(data, dict) or len(data) > 20:
        raise ValueError('invalid data')
    for key, value in data.items():
        if not isinstance(key, str) or len(key) > 64:
            raise ValueError('invalid field')
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError('invalid value')
        if isinstance(value, str) and len(value) > 4096:
            raise ValueError('oversized value')
    return event
