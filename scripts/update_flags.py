"""Refresh pinned local flag-icons SVGs and country names; verify npm SHA512."""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import urllib.request

VERSION = '7.6.0'
INTEGRITY = 'sha512-hir/PsXwr0EESyizKrXJzmkzpLIMf+1vlNKLqAfvdh+bsU94a7LYWTiubkHKqptGoCPzOUGcm6c4PfC9/BaGSQ=='
URL = f'https://registry.npmjs.org/flag-icons/-/flag-icons-{VERSION}.tgz'


def main():
    with urllib.request.urlopen(URL, timeout=60) as response:
        raw = response.read(16*1024**2+1)
    if len(raw) > 16*1024**2:
        raise ValueError('Flag archive exceeds limit')
    if 'sha512-' + base64.b64encode(hashlib.sha512(raw).digest()).decode() != INTEGRITY:
        raise ValueError('Flag archive integrity mismatch')
    target = Path(__file__).resolve().parents[1]/'static/flags'
    target.mkdir(exist_ok=True)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
        countries = json.load(tar.extractfile('package/country.json'))
        names = {}
        for country in countries:
            code = country['code']
            if not country.get('iso') or not re.fullmatch('[a-z]{2}',code):
                continue
            member = tar.getmember(f'package/flags/4x3/{code}.svg')
            if not member.isfile() or member.size > 1024**2:
                raise ValueError('Invalid SVG asset')
            asset = tar.extractfile(member).read()
            filename = code+'.svg'
            (target/filename).write_bytes(asset)
            files[filename] = hashlib.sha256(asset).hexdigest()
            names[code.upper()] = country['name']
        (target/'LICENSE').write_bytes(tar.extractfile('package/LICENSE').read())
    (target/'countries.json').write_text(json.dumps(names,sort_keys=True,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
    (target/'manifest.json').write_text(json.dumps({'package':'flag-icons','version':VERSION,'tarball':URL,
        'integrity':INTEGRITY,'files_sha256':files},sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(f'Verified {len(names)} local flags from flag-icons {VERSION}')


if __name__ == '__main__':
    main()
