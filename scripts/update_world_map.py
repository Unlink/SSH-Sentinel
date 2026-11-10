"""Generate local SVG country paths from a SHA256-pinned Natural Earth snapshot."""
import hashlib
import json
import math
from pathlib import Path
import re
import urllib.request

URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_admin_0_countries.geojson'
SHA256 = '6866c877d39cba9c357620878839b336d569f8c662d3cfab4cb1dbe2d39c977f'


def country_paths(source):
    shapes = []
    for feature in source['features']:
        geometry = feature['geometry']
        if geometry['type'] not in ('Polygon', 'MultiPolygon'):
            raise ValueError('Unsupported geometry')
        polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
        paths = []
        for polygon in polygons:
            for ring in polygon:
                if len(ring) < 4:
                    raise ValueError('Invalid polygon ring')
                coordinates = []
                for longitude, latitude in ring:
                    if (not math.isfinite(longitude) or not math.isfinite(latitude)
                            or abs(longitude) > 180.0001 or abs(latitude) > 90.0001):
                        raise ValueError('Invalid map coordinate')
                    x = (max(-180, min(180, longitude)) + 180) * 960 / 360
                    y = (90 - max(-90, min(90, latitude))) * 480 / 180
                    coordinates.append(f'{x:.1f},{y:.1f}')
                paths.append('M' + 'L'.join(coordinates) + 'Z')
        code = feature['properties']['ISO_A2_EH']
        shapes.append({'code': code if re.fullmatch('[A-Z]{2}', code) else '',
                       'name': feature['properties']['ADMIN'], 'path': ''.join(paths)})
    return shapes


def main():
    request = urllib.request.Request(URL, headers={'User-Agent': 'SSH-Sentinel-world-map'})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read(4 * 1024**2 + 1)
    if len(raw) > 4 * 1024**2 or hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError('Map source size/checksum mismatch')
    shapes = country_paths(json.loads(raw))
    target = Path(__file__).resolve().parents[1] / 'static/map'
    target.mkdir(exist_ok=True)
    compiled = (json.dumps(shapes, ensure_ascii=True, separators=(',', ':')) + '\n').encode()
    (target / 'countries.json').write_bytes(compiled)
    manifest = {'source': 'Natural Earth', 'version': '5.1.2', 'scale': '1:110m',
                'license': 'Public domain', 'license_url': 'https://www.naturalearthdata.com/about/terms-of-use/',
                'url': URL, 'source_sha256': SHA256, 'countries_sha256': hashlib.sha256(compiled).hexdigest(),
                'projection': 'Equirectangular, 960 by 480', 'features': len(shapes)}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (target / 'LICENSE').write_text('Natural Earth data is in the public domain.\n'
        'Source: https://www.naturalearthdata.com/\n'
        'Terms: https://www.naturalearthdata.com/about/terms-of-use/\n'
        'Local adaptation: projected/rounded to SVG country paths.\n', encoding='utf-8')
    print(f'Verified and generated {len(shapes)} country shapes ({len(compiled)} bytes)')


if __name__ == '__main__':
    main()
