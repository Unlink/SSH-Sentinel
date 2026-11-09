"""Refresh explicitly pinned npm browser assets, verifying registry SHA512 tarball integrity."""
import base64
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

PACKAGES = {
    'htmx.org': ('2.0.11', {'package/dist/htmx.min.js': 'htmx.min.js', 'package/LICENSE': 'HTMX-LICENSE'}),
    'chart.js': ('4.6.1', {'package/dist/chart.umd.min.js': 'chart.umd.js', 'package/LICENSE.md': 'CHARTJS-LICENSE.md'}),
}


def main():
    target = Path(__file__).resolve().parents[1] / 'static' / 'vendor'
    manifest = {}
    for package, (version, assets) in PACKAGES.items():
        with urllib.request.urlopen(f'https://registry.npmjs.org/{package}/{version}', timeout=30) as response:
            metadata = json.load(response)
        distribution = metadata['dist']
        with urllib.request.urlopen(distribution['tarball'], timeout=30) as response:
            archive = response.read(16 * 1024**2 + 1)
        if len(archive) > 16 * 1024**2:
            raise ValueError('Archive exceeds limit')
        actual = 'sha512-' + base64.b64encode(hashlib.sha512(archive).digest()).decode()
        if actual != distribution['integrity']:
            raise ValueError('Registry integrity mismatch')
        records = {}
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
            for member, filename in assets.items():
                info = tar.getmember(member)
                if not info.isfile() or info.size > 2 * 1024**2:
                    raise ValueError('Invalid browser asset')
                # Read only known regular members. Never extract paths from the archive.
                raw = tar.extractfile(info).read()
                (target / filename).write_bytes(raw)
                records[filename] = hashlib.sha256(raw).hexdigest()
        manifest[package] = {'version': version, 'tarball': distribution['tarball'],
                             'integrity': actual, 'files_sha256': records}
        print(f'Updated {package} {version}; SHA512 verified')
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
