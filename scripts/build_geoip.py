"""Compile SHA256-pinned DB-IP Lite snapshots into an offline SQLite asset."""
import argparse
import csv
from contextlib import closing
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import urllib.request

MAX_ARCHIVE = 64 * 1024**2
MAX_UNPACKED = 512 * 1024**2
MAX_ROWS = 5000000


def fetch_source(spec, kind, directory):
    pattern = rf'https://download\.db-ip\.com/free/dbip-{kind}-lite-\d{{4}}-\d{{2}}\.csv\.gz'
    if kind not in ('country', 'asn') or not re.fullmatch(pattern, spec['url']):
        raise ValueError('Invalid source URL')
    if not re.fullmatch('[0-9a-f]{64}', spec['sha256']):
        raise ValueError('Invalid source checksum')
    target = Path(directory) / f'{kind}.csv.gz'
    if target.exists():
        with target.open('rb') as stream:
            raw = stream.read(MAX_ARCHIVE + 1)
    else:
        request = urllib.request.Request(spec['url'], headers={
            'User-Agent': 'SSH-Sentinel/1.0 (offline enrichment dataset download)'})
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read(MAX_ARCHIVE + 1)
    if len(raw) > MAX_ARCHIVE:
        raise ValueError('Source archive exceeds size limit')
    if hashlib.sha256(raw).hexdigest() != spec['sha256']:
        raise ValueError('Source checksum mismatch')
    target.write_bytes(raw)
    return target


def csv_lines(path):
    unpacked = 0
    with gzip.open(path, 'rb') as stream:
        while raw := stream.readline(8193):
            unpacked += len(raw)
            if len(raw) > 8192 or unpacked > MAX_UNPACKED:
                raise ValueError('CSV size limit exceeded')
            yield raw.decode('utf-8')


def import_ranges(conn, kind, path):
    previous = {}
    batch = []
    count = 0
    csv.field_size_limit(4096)
    for row in csv.reader(csv_lines(path)):
        count += 1
        if count > MAX_ROWS or len(row) != (3 if kind == 'country' else 4):
            raise ValueError('Invalid CSV row or row limit exceeded')
        start, end = ipaddress.ip_address(row[0]), ipaddress.ip_address(row[1])
        if start.version != end.version or start > end:
            raise ValueError('Invalid address range')
        if start.version in previous and start <= previous[start.version]:
            raise ValueError('Unsorted or overlapping address ranges')
        previous[start.version] = end
        if kind == 'country':
            if not re.fullmatch('[A-Z]{2}', row[2]):
                raise ValueError('Invalid country code')
            values = (row[2],)
        else:
            if not row[2].isascii() or not row[2].isdecimal() or not 0 <= int(row[2]) <= 4294967295:
                raise ValueError('Invalid AS number')
            if len(row[3]) > 256:
                raise ValueError('AS organization exceeds limit')
            values = (int(row[2]), row[3])
        batch.append((start.version, start.packed, end.packed, *values))
        if len(batch) == 1000:
            conn.executemany(f'INSERT INTO {kind} VALUES ({",".join("?" for _ in batch[0])})', batch)
            batch.clear()
    if batch:
        conn.executemany(f'INSERT INTO {kind} VALUES ({",".join("?" for _ in batch[0])})', batch)
    if not count:
        raise ValueError('Empty source dataset')
    return count


def build_database(country_path, asn_path, output, manifest):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix='geoip-', suffix='.sqlite', dir=output.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with closing(sqlite3.connect(temporary)) as conn:
            conn.executescript('''
                PRAGMA journal_mode=OFF;
                PRAGMA synchronous=OFF;
                PRAGMA cache_size=-8192;
                PRAGMA user_version=1;
                CREATE TABLE country (version INTEGER, start BLOB, end BLOB, country_code TEXT,
                    PRIMARY KEY(version,start)) WITHOUT ROWID;
                CREATE TABLE asn (version INTEGER, start BLOB, end BLOB, asn INTEGER, asn_name TEXT,
                    PRIMARY KEY(version,start)) WITHOUT ROWID;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
            ''')
            for kind, path in [('country', country_path), ('asn', asn_path)]:
                count = import_ranges(conn, kind, path)
                conn.execute('INSERT INTO metadata VALUES (?,?)', (kind + '_rows', str(count)))
            conn.execute('INSERT INTO metadata VALUES (?,?)', ('release', manifest['release']))
            conn.execute('INSERT INTO metadata VALUES (?,?)', ('sources', json.dumps(manifest)))
            conn.commit()
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('geoip-sources.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-dir', type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as temporary:
        directory = args.source_dir or Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        files = {kind: fetch_source(manifest['files'][kind], kind, directory) for kind in ('country', 'asn')}
        build_database(files['country'], files['asn'], args.output, manifest)
    print(f'Built offline GeoIP/ASN snapshot {manifest["release"]}')


if __name__ == '__main__':
    main()
