"""Location-validated recommendation orchestration with reusable saved data."""
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta

from locations import lineage, normalize_name, resolve
from restaurant_service import ApiError, SerpClient, search_area
from recommendation_service import rank_restaurants
from storage import utcnow


def local_query(store, message, default_city='Đà Nẵng'):
    """Use a catalog-matched ward when the external query parser is unavailable."""
    normalized=' '+normalize_name(message)+' '
    with store.connect() as db:
        names=db.execute('''SELECT l.name,a.normalized_alias AS phrase FROM locations l
            JOIN location_aliases a ON a.location_id=l.id
            WHERE l.level='ward' AND l.is_active=1
            UNION SELECT name,normalized_name FROM locations
            WHERE level='ward' AND is_active=1''').fetchall()
    matches=[]
    for row in names:
        phrase=row['phrase']
        if len(phrase)>=4 and re.search(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)',normalized):
            matches.append((len(phrase),row['name']))
    ward=max(matches,default=(0,''))[1]
    return {'intent':'restaurant_recommendation','city':default_city or 'Đà Nẵng',
            'district':'','ward':ward,'street':'','cuisine':''}


def crawl_or_reuse(store,client,analyzer,place,cuisine='',limit=5,pages=1):
    """Reuse a successful crawl across calendar months while it remains fresh."""
    location_id=place['id']
    names=[x['name'] for x in lineage(store,location_id) if x['level']!='country']
    area=', '.join(reversed(names))
    query='nhà hàng '+(' '.join(cuisine.split())+' ' if cuisine.strip() else '')+'tại '+area
    month=datetime.now(timezone.utc).strftime('%Y-%m')
    digest=hashlib.sha256(f'{normalize_name(query)}|{limit}|{pages}'.encode()).hexdigest()
    with store.connect() as db:
        recent=db.execute('''SELECT * FROM crawl_runs WHERE location_id=? AND query=?
            AND provider='serpapi' AND status='success' AND search_id IS NOT NULL
            ORDER BY completed_at DESC LIMIT 1''',(location_id,query)).fetchone()
        if recent and recent['completed_at']:
            completed=datetime.fromisoformat(recent['completed_at'])
            if completed >= datetime.now(timezone.utc)-timedelta(days=60):
                return recent['search_id'],True
        row=db.execute('''SELECT * FROM crawl_runs WHERE location_id=? AND query_hash=?
            AND year_month=? AND provider='serpapi' ''',(location_id,digest,month)).fetchone()
        if row and row['status']=='success': return row['search_id'],True
        if row and row['status']=='running': raise ApiError('Khu vực này đang được cập nhật; thử lại sau.')
        db.execute('''INSERT INTO crawl_runs(location_id,query,query_hash,year_month,provider,status,started_at)
            VALUES(?,?,?,?,?,'running',?) ON CONFLICT(location_id,query_hash,year_month,provider)
            DO UPDATE SET status='running',started_at=excluded.started_at,error_message='',search_id=NULL''',
            (location_id,query,digest,month,'serpapi',utcnow()))
    try:
        sid=search_area(store,client,analyzer,area,cuisine,limit,pages,place=place)
        record=store.get_search(sid)
        # A failed review page must not force a complete re-crawl of an area
        # that already has enough saved evidence for recommendations.
        usable=sum(item['assessment']['n'] >= 8 for item in record['result']['restaurants'])
        complete=record['status']=='success' or usable>=3
        with store.connect() as db:
            for item in record['result']['restaurants']:
                db.execute('INSERT OR IGNORE INTO restaurant_locations VALUES(?,?)',(item['id'],location_id))
            db.execute('''UPDATE crawl_runs SET status=?,completed_at=?,result_count=?,search_id=?,error_message=?
                WHERE location_id=? AND query_hash=? AND year_month=? AND provider='serpapi' ''',
                ('success' if complete else 'failed',utcnow(),len(record['result']['restaurants']),sid,
                 '; '.join(record['result'].get('warnings',[]))[:300],location_id,digest,month))
        return sid,False
    except Exception as exc:
        with store.connect() as db:
            db.execute('''UPDATE crawl_runs SET status='failed',completed_at=?,error_message=?
                WHERE location_id=? AND query_hash=? AND year_month=? AND provider='serpapi' ''',
                (utcnow(),str(exc)[:300],location_id,digest,month))
        raise


def local_candidates(store,place,limit=25):
    chain=lineage(store,place['id'])
    names=[normalize_name(x['name']).replace('phuong ','').replace('xa ','')
           for x in chain if x['level'] not in {'country','province'}]
    with store.connect() as db:
        linked=[dict(r) for r in db.execute('''SELECT r.* FROM restaurants r
            JOIN restaurant_locations l ON l.restaurant_id=r.id WHERE l.location_id=?
            ORDER BY r.rating DESC LIMIT ?''',(place['id'],limit))]
        if linked: return linked
        all_rows=[dict(r) for r in db.execute('SELECT * FROM restaurants ORDER BY rating DESC')]
    if not names: return all_rows[:limit]
    return [r for r in all_rows if all(n in normalize_name(r['address']) for n in names)][:limit]


def recommend(store,analyzer,profile,memory,feedback,place,cuisine=''):
    rows=local_candidates(store,place)
    if cuisine:
        needle=normalize_name(cuisine)
        rows=[r for r in rows if needle in normalize_name(r['category']+' '+r['name'])]
    items=[]
    for row in rows[:15]:
        row['assessment']=analyzer.assess(store,row['id'])
        items.append(row)
    ranked=rank_restaurants(items,{**profile,'cuisine':cuisine or profile.get('cuisine','')},
                            memory,feedback,config='E')
    return ranked[:5]


def ensure_history_table(store):
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS assistant_messages (
            id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES accounts(id),
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),content TEXT NOT NULL,
            context_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_assistant_user ON assistant_messages(user_id,id)')


def history(store,user_id):
    with store.connect() as db:
        rows=db.execute('''SELECT role,content,context_json,created_at FROM
            (SELECT * FROM assistant_messages WHERE user_id=? ORDER BY id DESC LIMIT 30) ORDER BY created_at,id''',
            (user_id,)).fetchall()
        return [{**dict(r),'context':json.loads(r['context_json'])} for r in rows]


def save_turn(store,user_id,message,reply,context):
    with store.connect() as db:
        stamp=utcnow()
        db.execute('INSERT INTO assistant_messages(user_id,role,content,created_at) VALUES(?,?,?,?)',
                   (user_id,'user',message,stamp))
        db.execute('''INSERT INTO assistant_messages(user_id,role,content,context_json,created_at)
            VALUES(?,?,?,?,?)''',(user_id,'assistant',reply,json.dumps(context,ensure_ascii=False),stamp))
