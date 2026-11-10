"""Read-only local IP enrichment. No DNS, downloads or external lookup requests."""
from collections import Counter
from contextlib import closing
from functools import lru_cache
import ipaddress
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]


class GeoIP:
    def __init__(self, path):
        self.path = Path(path)
        self.release = None
        self.available = False
        self.countries = json.loads((ROOT / 'static/flags/countries.json').read_text(encoding='utf-8'))
        try:
            with closing(self.connect()) as conn:
                if conn.execute('PRAGMA user_version').fetchone()[0] != 1:
                    raise ValueError('Unsupported GeoIP format')
                conn.execute('SELECT version,start,end,country_code FROM country LIMIT 0')
                conn.execute('SELECT version,start,end,asn,asn_name FROM asn LIMIT 0')
                row = conn.execute("SELECT value FROM metadata WHERE key='release'").fetchone()
                self.release = row[0] if row else None
                self.available = bool(self.release)
        except (OSError, sqlite3.Error, ValueError):
            pass
        self.lookup = lru_cache(maxsize=4096)(self._lookup)

    def connect(self):
        conn = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA cache_size=-2048')
            return conn
        except sqlite3.Error:
            conn.close()
            raise

    @staticmethod
    def public_address(value):
        address = ipaddress.ip_address(value)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if (not address.is_global or address.is_multicast or address.is_reserved
                or (isinstance(address, ipaddress.IPv6Address) and address.is_site_local)):
            return None
        return address

    def country_totals(self, weighted_ips):
        """One country-only connection for the complete bounded event population."""
        total = sum(row['count'] for row in weighted_ips)
        unknown = {'countries': [], 'total_connections': total, 'unknown_connections': total}
        if not self.available or not weighted_ips:
            return unknown
        counts = Counter()
        try:
            with closing(self.connect()) as conn:
                for item in weighted_ips:
                    address = self.public_address(item['ip'])
                    if address is None:
                        continue
                    row = conn.execute('SELECT end,country_code FROM country WHERE version=? AND start<=? '
                                       'ORDER BY start DESC LIMIT 1', (address.version, address.packed)).fetchone()
                    if row and address.packed <= row['end'] and row['country_code'] in self.countries:
                        counts[row['country_code']] += item['count']
        except (OSError, sqlite3.Error, ValueError, TypeError):
            return unknown
        countries = [{'code': code, 'name': self.countries[code], 'count': count}
                     for code, count in sorted(counts.items(), key=lambda row: (-row[1], row[0]))]
        return {'countries': countries, 'total_connections': total,
                'unknown_connections': total-sum(counts.values())}

    def _lookup(self, value):
        result = {'country_code': None, 'country_name': None, 'asn': None,
                  'asn_name': None, 'status': 'unknown'}
        try:
            address = self.public_address(value)
        except ValueError:
            return dict(result, status='invalid')
        if address is None:
            return dict(result, status='non_public')
        if not self.available:
            return dict(result, status='unavailable')
        try:
            with closing(self.connect()) as conn:
                for kind in ('country', 'asn'):
                    row = conn.execute(f'SELECT * FROM {kind} WHERE version=? AND start<=? '
                                       'ORDER BY start DESC LIMIT 1', (address.version, address.packed)).fetchone()
                    if not row or address.packed > row['end']:
                        continue
                    if kind == 'country' and row['country_code'] in self.countries:
                        result['country_code'] = row['country_code']
                        result['country_name'] = self.countries[row['country_code']]
                    elif kind == 'asn' and isinstance(row['asn'], int) and 0 < row['asn'] <= 4294967295:
                        result['asn'] = row['asn']
                        result['asn_name'] = str(row['asn_name'])[:256]
        except (OSError, sqlite3.Error, TypeError):
            return dict(result, status='unavailable')
        if result['country_code'] or result['asn']:
            result['status'] = 'found'
        return result
