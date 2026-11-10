"""Tiny local datasets exercise offline range lookup and input validation."""
import gzip
from contextlib import closing
import json
import sqlite3
from pathlib import Path

import pytest


def make_dataset(tmp_path,country=None,asn=None):
    from scripts.build_geoip import build_database
    countries=country if country is not None else (
        '1.1.1.0,1.1.1.255,AU\n8.8.8.0,8.8.8.255,US\n2606:4700::,2606:4700:ffff:ffff:ffff:ffff:ffff:ffff,US\n')
    networks=asn if asn is not None else (
        '1.1.1.0,1.1.1.255,13335,Cloudflare\n8.8.8.0,8.8.8.255,15169,Google\n2606:4700::,2606:4700:ffff:ffff:ffff:ffff:ffff:ffff,13335,Cloudflare\n')
    country_path,asn_path=tmp_path/'country.gz',tmp_path/'asn.gz'
    country_path.write_bytes(gzip.compress(countries.encode()))
    asn_path.write_bytes(gzip.compress(networks.encode()))
    output=tmp_path/'geoip.sqlite'
    build_database(country_path,asn_path,output,{'release':'2026-11'})
    return output


def test_ipv4_ipv6_boundaries_gaps_and_mapped_ip(tmp_path):
    from app.web.geoip import GeoIP
    geo=GeoIP(make_dataset(tmp_path))
    for ip in ('1.1.1.0','1.1.1.1','1.1.1.255','::ffff:1.1.1.1'):
        row=geo.lookup(ip)
        assert row['country_code']=='AU' and row['asn']==13335
        assert row['country_name']=='Australia' and row['asn_name']=='Cloudflare'
    assert geo.lookup('2606:4700:4700::1111')['asn']==13335
    assert geo.lookup('1.1.2.0')['status']=='unknown'
    assert geo.lookup('1.1.0.255')['country_code'] is None
    assert geo.release=='2026-11' and geo.available
    assert geo.lookup.cache_info().maxsize==4096


@pytest.mark.parametrize('ip',['127.0.0.1','172.30.222.1','192.0.2.1','::1','fc00::1','224.0.0.1','ff02::1','0.0.0.0','4000::1','64:ff9b::1','fec0::1'])
def test_nonpublic_addresses_never_get_country_flags(tmp_path,ip):
    from app.web.geoip import GeoIP
    geo=GeoIP(make_dataset(tmp_path))
    result=geo.lookup(ip)
    assert result['status']=='non_public'
    assert result['country_code'] is None and result['asn'] is None


def test_missing_corrupt_data_and_invalid_ip_degrade_gracefully(tmp_path):
    from app.web.geoip import GeoIP
    geo=GeoIP(tmp_path/'missing.sqlite')
    assert not geo.available and geo.lookup('1.1.1.1')['status']=='unavailable'
    assert geo.lookup('not-an-ip')['status']=='invalid'
    broken=tmp_path/'broken.sqlite'
    broken.write_bytes(b'not sqlite')
    assert GeoIP(broken).lookup('1.1.1.1')['status']=='unavailable'


def test_partial_lookup_and_malicious_country_code(tmp_path):
    from app.web.geoip import GeoIP
    db=make_dataset(tmp_path,country='1.1.1.0,1.1.1.255,ZZ\n',asn='8.8.8.0,8.8.8.255,15169,Google\n')
    geo=GeoIP(db)
    assert geo.lookup('1.1.1.1')['country_code'] is None
    row=geo.lookup('8.8.8.8')
    assert row['country_code'] is None and row['asn']==15169
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("UPDATE country SET country_code='../evil'")
        conn.commit()
    assert GeoIP(db).lookup('1.1.1.1')['country_code'] is None


@pytest.mark.parametrize('country,asn',[
    ('1.1.1.1,1.1.1.0,US\n',None),
    ('1.1.1.0,1.1.1.255,US\n1.1.1.1,1.1.2.0,US\n',None),
    ('1.1.1.0,::1,US\n',None),
    ('1.1.1.0,1.1.1.255,../../US\n',None),
    (None,'1.1.1.0,1.1.1.255,4294967296,Invalid ASN\n'),
    (None,'1.1.1.0,1.1.1.255,13335,'+'x'*9000+'\n'),
])
def test_builder_rejects_invalid_or_overlapping_rows(tmp_path,country,asn):
    with pytest.raises(ValueError):
        make_dataset(tmp_path,country,asn)
    assert not (tmp_path/'geoip.sqlite').exists()


def test_download_checksum_and_destination_validation(tmp_path,monkeypatch):
    import io
    from scripts.build_geoip import fetch_source
    import urllib.request
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k:io.BytesIO(b'bad archive'))
    spec={'url':'https://download.db-ip.com/free/dbip-country-lite-2026-11.csv.gz','sha256':'0'*64}
    with pytest.raises(ValueError,match='checksum'):
        fetch_source(spec,'country',tmp_path)
    with pytest.raises(ValueError,match='source URL'):
        fetch_source({'url':'http://127.0.0.1/private','sha256':'0'*64},'country',tmp_path)


def test_malformed_database_schema_degrades_without_raising(tmp_path):
    from app.web.geoip import GeoIP
    path=tmp_path/'bad-schema.sqlite'
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript("""PRAGMA user_version=1;
            CREATE TABLE metadata(key TEXT,value TEXT);
            INSERT INTO metadata VALUES('release','2026-11');
            CREATE TABLE country(version INTEGER,start BLOB,country_code TEXT);
            INSERT INTO country VALUES(4,x'01010100','AU');""")
        conn.commit()
    geo=GeoIP(path)
    assert geo.lookup('1.1.1.1')['status']=='unavailable'
