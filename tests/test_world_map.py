"""Country totals count all accepted SSH sources, within the selected time window."""
import json
from datetime import datetime,timedelta,timezone

from app.web.database import Database
from app.web.ingestion import Importer
from app.web.analytics import summary
from app.web.geoip import GeoIP
from tests.test_geoip import make_dataset
from tests.test_ingestion import event


def test_country_map_uses_all_sources_not_just_top_ten_and_counts_connections(tmp_path):
    geo=GeoIP(make_dataset(tmp_path))
    db=Database(tmp_path/'events.sqlite')
    spool=tmp_path/'events'
    spool.mkdir()
    entries=[]
    for n in range(12):
        e=event();e['ip']=f'1.1.1.{n+1}';entries.append(e)
    for ip,kind in [('8.8.8.8','connection'),('172.30.222.1','connection'),('1.1.2.1','connection'),('8.8.8.8','auth_attempt')]:
        e=event(kind);e['ip']=ip;entries.append(e)
    old=event();old['ip']='8.8.8.8';old['ts']=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat();entries.append(old)
    (spool/'map.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in entries))
    Importer(db,spool).run()
    result=summary(db,1,geoip=geo)
    assert len(result['top_ips'])==10
    totals=result['origins']
    assert {r['code']:r['count'] for r in totals['countries']}=={'AU':12,'US':1}
    assert totals['unknown_connections']==2 and totals['total_connections']==result['connections']==15
    seven=summary(db,7,geoip=geo)['origins']
    assert {r['code']:r['count'] for r in seven['countries']}=={'AU':12,'US':2}
    assert seven['total_connections']==16


def test_map_intensity_and_missing_small_country_counts():
    from app.web.world_map import map_view
    view=map_view({'countries':[{'code':'US','name':'United States','count':20},
        {'code':'SK','name':'Slovakia','count':1},{'code':'SG','name':'Singapore','count':3}],
        'unknown_connections':2,'total_connections':26})
    active={r['code']:r for r in view['shapes'] if r['count']}
    assert active['US']['level']==5 and 1<=active['SK']['level']<5
    assert view['mapped_connections']==21 and view['not_drawn_connections']==3
    assert all(r['level']==0 for r in view['shapes'] if r['count']==0)
    assert view['unknown_connections']==2
    assert any(r['code']=='SG' and not r['drawn'] for r in view['countries'])


def test_map_asset_has_safe_geometry_and_known_landmarks():
    from app.web.world_map import load_shapes
    import re
    shapes=load_shapes()
    assert len(shapes)>=170
    codes={shape['code'] for shape in shapes}
    assert {'US','SK','CN','AU','RU','FR','NO','AQ'}<=codes
    for shape in shapes:
        assert not shape['code'] or re.fullmatch('[A-Z]{2}',shape['code'])
        assert re.fullmatch(r'[MLZ0-9., -]+',shape['path'])
