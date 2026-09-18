"""Versioned Vietnamese place names and conservative local validation."""
import json
import re
import unicodedata
from pathlib import Path

from storage import utcnow

ROOT = Path(__file__).resolve().parent.parent


def normalize_name(value):
    value = unicodedata.normalize('NFD', str(value or '').replace('Đ', 'D').replace('đ', 'd'))
    value = ''.join(c for c in value if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def upsert(db, code, name, parent_id, level, source, source_id='', effective_from=None):
    stamp = utcnow()
    db.execute('''INSERT INTO locations(code,name,normalized_name,parent_id,level,source,source_id,
        effective_from,imported_at) VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(code) DO UPDATE SET name=excluded.name,normalized_name=excluded.normalized_name,
        parent_id=excluded.parent_id,level=excluded.level,source=excluded.source,
        source_id=excluded.source_id,effective_from=excluded.effective_from,
        imported_at=excluded.imported_at''',
        (code,name,normalize_name(name),parent_id,level,source,source_id,effective_from,stamp))
    return db.execute('SELECT id FROM locations WHERE code=?',(code,)).fetchone()['id']


def alias(db, location_id, name):
    db.execute('INSERT OR IGNORE INTO location_aliases VALUES(?,?,?)',
               (location_id,name,normalize_name(name)))


def seed_danang(store):
    units=json.loads((ROOT/'location_data'/'danang_2025.json').read_text(encoding='utf-8'))
    streets=json.loads((ROOT/'location_data'/'danang_osm_streets.json').read_text(encoding='utf-8'))
    with store.connect() as db:
        country=upsert(db,'VN','Việt Nam',None,'country',units['source'],'VN')
        alias(db,country,'Vietnam')
        city=upsert(db,'VN-DN','Đà Nẵng',country,'province',units['source'],'VN-DN','2025-07-01')
        for name in ('Da Nang','Danang','Thành phố Đà Nẵng'):
            alias(db,city,name)
        for unit in units['units']:
            prefix=unit['level']+' '
            lid=upsert(db,f"VN-DN-{unit['code']:03d}",prefix+unit['name'],city,'ward',
                       units['source'],
                       f"article-1-item-{unit['code']}" if unit['code']<=92 else 'article-1-item-93-unchanged',
                       units['effective_from'])
            alias(db,lid,unit['name'])
        # OSM highway ways often repeat a road; keep one city-level street per name.
        distinct={}
        for street in streets['streets']:
            name=str(street['name']).strip()
            key=normalize_name(name)
            if key and len(key)>=3: distinct.setdefault(key,street)
        for key,street in distinct.items():
            upsert(db,'OSM-DN-'+key,street['name'],city,'street',streets['source'],
                   street['source_id'])
        # Pre-2025 districts are aliases to their same-named successor wards.
        for old in ('Hải Châu','Sơn Trà','Thanh Khê','Cẩm Lệ','Liên Chiểu','Ngũ Hành Sơn'):
            row=db.execute('SELECT id FROM locations WHERE parent_id=? AND level=? AND normalized_name=?',
                           (city,'ward',normalize_name('phường '+old))).fetchone()
            if row: alias(db,row['id'],'quận '+old)
        wards={normalize_name(x['name'].split(' ',1)[1]):x['id'] for x in db.execute(
            "SELECT id,name FROM locations WHERE parent_id=? AND level='ward'",(city,))}
        roads={x['normalized_name']:x['id'] for x in db.execute(
            "SELECT id,normalized_name FROM locations WHERE parent_id=? AND level='street'",(city,))}
        for restaurant in db.execute('SELECT id,address FROM restaurants').fetchall():
            address=restaurant['address'] or ''
            normalized=normalize_name(address)
            if 'da nang' not in normalized: continue
            db.execute('INSERT OR IGNORE INTO restaurant_locations VALUES(?,?)',(restaurant['id'],city))
            parts=[normalize_name(p) for p in address.split(',')]
            for part in parts[1:]:
                if part in wards:
                    db.execute('INSERT OR IGNORE INTO restaurant_locations VALUES(?,?)',
                               (restaurant['id'],wards[part]))
            first=re.sub(r'^\d+[a-z]?(?:/\d+)?\s+', '',address.split(',')[0],flags=re.I)
            first=re.sub(r'^(?:đường|đ\.|ngõ|ng\.)\s*','',first,flags=re.I)
            road=roads.get(normalize_name(first))
            if road:
                db.execute('INSERT OR IGNORE INTO restaurant_locations VALUES(?,?)',(restaurant['id'],road))
    return {'wards':len(units['units']),'streets':len(distinct)}


def children(store,parent_id=None):
    with store.connect() as db:
        if parent_id is None:
            rows=db.execute('SELECT id,name,level FROM locations WHERE parent_id IS NULL AND is_active=1 ORDER BY name')
        else:
            rows=db.execute('SELECT id,name,level FROM locations WHERE parent_id=? AND is_active=1 ORDER BY name',
                            (parent_id,))
        return [dict(r) for r in rows]


def place(store,location_id):
    with store.connect() as db:
        row=db.execute('SELECT * FROM locations WHERE id=? AND is_active=1',(location_id,)).fetchone()
        return dict(row) if row else None


def lineage(store,location_id):
    result=[]
    with store.connect() as db:
        while location_id:
            row=db.execute('SELECT * FROM locations WHERE id=? AND is_active=1',(location_id,)).fetchone()
            if not row: return []
            result.append(dict(row));location_id=row['parent_id']
    return list(reversed(result))


def resolve(store,city=None,district=None,ward=None,street=None):
    """Return the deepest validated place; never infer a missing street or ward."""
    if not city: return None
    # OSM street ways have no reliable ward assignment in this snapshot.
    if street and (ward or district): return None
    if ward and district and normalize_name(ward)!=normalize_name(district): return None
    with store.connect() as db:
        parent=None
        for level,value in (('province',city),('ward',ward or district),('street',street)):
            if not value: continue
            norm=normalize_name(value)
            if level=='province':
                rows=db.execute('''SELECT DISTINCT l.* FROM locations l LEFT JOIN location_aliases a ON a.location_id=l.id
                    WHERE l.level='province' AND l.is_active=1 AND (l.normalized_name=? OR a.normalized_alias=?)''',(norm,norm)).fetchall()
            else:
                # Streets from OSM are linked at city level because way-to-ward geometry is unavailable.
                owner=parent if level=='ward' else city_id
                rows=db.execute('''SELECT DISTINCT l.* FROM locations l LEFT JOIN location_aliases a ON a.location_id=l.id
                    WHERE l.parent_id=? AND l.level=? AND l.is_active=1
                    AND (l.normalized_name=? OR a.normalized_alias=?)''',(owner,level,norm,norm)).fetchall()
            if len(rows)!=1: return None
            parent=rows[0]['id']
            if level=='province': city_id=parent
        return dict(rows[0]) if parent else None


def resolve_area_text(store,area):
    """Validate the legacy search box without trusting arbitrary free-form text."""
    parts=[x.strip() for x in area.split(',') if x.strip()]
    if not 1<=len(parts)<=2: return None
    for city_part in parts:
        city=resolve(store,city=city_part)
        if city and city['level']=='province':
            other=[x for x in parts if x!=city_part]
            if not other: return city
            return (resolve(store,city=city_part,ward=other[0]) or
                    resolve(store,city=city_part,street=other[0]))
    return None
