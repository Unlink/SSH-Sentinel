"""Local country shape presentation; never contacts a map service."""
from functools import lru_cache
import json
import math
from pathlib import Path


@lru_cache(maxsize=1)
def load_shapes():
    path = Path(__file__).resolve().parents[2] / 'static/map/countries.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []


def map_view(origins):
    shapes = load_shapes()
    drawn = {shape['code'] for shape in shapes if shape['code']}
    counts = {row['code']: row['count'] for row in origins['countries']}
    maximum = max(counts.values(), default=0)
    countries = [dict(row, drawn=row['code'] in drawn) for row in origins['countries']]
    display = []
    for shape in shapes:
        count = counts.get(shape['code'], 0)
        level = 1 + min(4, int(4 * math.log1p(count) / math.log1p(maximum))) if count else 0
        display.append(dict(shape, count=count, level=level))
    not_drawn = sum(row['count'] for row in countries if not row['drawn'])
    return dict(origins, shapes=display, countries=countries,
                mapped_connections=origins['total_connections'] - origins['unknown_connections'] - not_drawn,
                not_drawn_connections=not_drawn)
