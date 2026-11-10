"""Indexed aggregate queries, with UTC buckets and bounded top lists."""
from datetime import datetime, timedelta, timezone


def summary(db, days=1, *, geoip=None):
    days = days if days in (1, 7, 30) else 1
    now = datetime.now(timezone.utc)
    hourly = days == 1
    start = now.replace(minute=0, second=0, microsecond=0) if hourly else now.replace(hour=0, minute=0, second=0, microsecond=0)
    length = 24 if hourly else days
    step = timedelta(hours=1) if hourly else timedelta(days=1)
    start -= step * (length - 1)
    since = start.isoformat(timespec='milliseconds')
    result = {'connections': 0, 'attempts': 0, 'shells': 0, 'unique_ips': 0, 'unauthenticated': 0}
    with db.connect() as conn:
        counts = {r['kind']: r['n'] for r in conn.execute('SELECT kind, count(*) n FROM events WHERE ts>=? GROUP BY kind', (since,))}
        result.update(connections=counts.get('connection', 0), attempts=counts.get('auth_attempt', 0), shells=counts.get('shell_start', 0))
        result['unique_ips'] = conn.execute('SELECT count(DISTINCT ip) FROM events WHERE ts>=?', (since,)).fetchone()[0]
        result['unauthenticated'] = conn.execute("SELECT count(*) FROM events WHERE ts>=? AND kind='disconnect' AND json_extract(data, '$.authenticated')=0", (since,)).fetchone()[0]
        for key, expression, kind in [('top_ips', 'ip', 'connection'),
                ('top_users', "json_extract(data, '$.username')", 'auth_attempt'),
                ('top_commands', "json_extract(data, '$.command')", 'command')]:
            result[key] = [dict(r) for r in conn.execute(f'SELECT {expression} label, count(*) count FROM events WHERE ts>=? AND kind=? GROUP BY label ORDER BY count DESC, label LIMIT 10', (since, kind))]
        if geoip is not None:
            weighted_ips = [dict(row) for row in conn.execute(
                "SELECT ip,count(*) count FROM events WHERE ts>=? AND kind='connection' GROUP BY ip", (since,))]
        width = 13 if hourly else 10
        rows = conn.execute('SELECT substr(ts,1,?) bucket, kind, count(*) n FROM events WHERE ts>=? AND kind IN (\'connection\',\'auth_attempt\') GROUP BY bucket, kind', (width, since))
        counts = {(r['bucket'], r['kind']): r['n'] for r in rows}
        result['activity'] = []
        for i in range(length):
            stamp = (start + i * step).isoformat()[:width]
            result['activity'].append({'time': stamp, 'connections': counts.get((stamp, 'connection'), 0),
                                       'attempts': counts.get((stamp, 'auth_attempt'), 0)})
    if geoip is not None:
        result['origins'] = geoip.country_totals(weighted_ips)
    return result
