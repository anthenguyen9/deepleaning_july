"""Location-validated, monthly-cached recommendation orchestration."""
import hashlib
import json
from datetime import datetime, timezone

from locations import lineage, normalize_name, resolve
from restaurant_service import ApiError, SerpClient, search_area
from recommendation_service import rank_restaurants
from storage import utcnow


def crawl_or_reuse(store,client,analyzer,place,cuisine='',limit=5,pages=1):
    """Reserve one location/query/month; failed runs can be retried."""
    location_id=place['id']
    names=[x['name'] for x in lineage(store,location_id) if x['level']!='country']
    area=', '.join(reversed(names))
    query='nhà hàng '+(' '.join(cuisine.split())+' ' if cuisine.strip() else '')+'tại '+area
    month=datetime.now(timezone.utc).strftime('%Y-%m')
    digest=hashlib.sha256(f'{normalize_name(query)}|{limit}|{pages}'.encode()).hexdigest()
    with store.connect() as db:
        row=db.execute('''SELECT * FROM crawl_runs WHERE location_id=? AND query_hash=?
            AND year_month=? AND provider='serpapi' ''',(location_id,digest,month)).fetchone()
        if row and row['status']=='success': return row['search_id'],True
        if row and row['status']=='running': raise ApiError('Khu vực này đang được cập nhật; thử lại sau.')
        db.execute('''INSERT INTO crawl_runs(location_id,query,query_hash,year_month,provider,status,started_at)
            VALUES(?,?,?,?,?,'running',?) ON CONFLICT(location_id,query_hash,year_month,provider)
            DO UPDATE SET status='running',started_at=excluded.started_at,error_message='',search_id=NULL''',
            (location_id,query,digest,month,'serpapi',utcnow()))
    try:
        sid=search_area(store,client,analyzer,area,cuisine,limit,pages)
        record=store.get_search(sid)
        complete=record['status']=='success'
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
