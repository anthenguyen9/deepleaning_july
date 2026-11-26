"""Bounded SerpApi ingestion, cached evidence, and explicit model provenance."""
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from pipeline import ASPECTS, normalize
from locations import normalize_name

def now():
    return datetime.now(timezone.utc).isoformat()

def encode(value):
    return json.dumps(value, ensure_ascii=False)

def safe_url(value):
    if not isinstance(value, str): return ''
    url = urllib.parse.urlsplit(value)
    return value if url.scheme == 'https' and url.hostname and not url.username else ''

def sanitize(value, secret=''):
    if isinstance(value, dict):
        return {k:sanitize(v,secret) for k,v in value.items() if k.lower() not in
                {'api_key','key','authorization','user','contributor_id','profile_photo','thumbnail'}}
    if isinstance(value, list): return [sanitize(x,secret) for x in value]
    if isinstance(value, str):
        if secret: value = value.replace(secret, '[REDACTED]')
        return re.sub(r'(?i)(api_key=)[^&\s]+', r'\1[REDACTED]', value)
    return value

class ApiError(Exception): pass

class SerpClient:
    def __init__(self, store, key=None, transport=None, ttl_hours=24, daily_limit=30):
        self.store, self.key = store, key if key is not None else os.getenv('SERPAPI_API_KEY','').strip()
        self.transport = transport or self._request
        self.ttl_hours, self.daily_limit = ttl_hours, daily_limit
        self.calls = self.hits = 0

    def _request(self, params):
        url = 'https://serpapi.com/search.json?' + urllib.parse.urlencode({**params,'api_key':self.key})
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            # Do not surface URL, body, or exception strings containing credentials.
            raise ApiError({401:'API key không hợp lệ.',403:'API bị từ chối truy cập.',
                429:'Đã hết hạn mức hoặc bị giới hạn tốc độ.'}.get(e.code,f'SerpApi trả HTTP {e.code}.')) from None
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise ApiError('Không thể đọc phản hồi SerpApi. Kiểm tra mạng và thử lại.') from None

    def fetch(self, params):
        cache_key = hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM api_cache WHERE cache_key=?',(cache_key,)).fetchone()
        if row and (datetime.now(timezone.utc)-datetime.fromisoformat(row['fetched_at'])).total_seconds()<self.ttl_hours*3600:
            self.hits += 1
            return json.loads(row['payload']), row['fetched_at']
        if not self.key: raise ApiError('Chưa cấu hình SERPAPI_API_KEY. Chạy src/configure_key.py rồi khởi động lại web.')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            used = db.execute('SELECT COUNT(*) FROM api_calls WHERE created_at>=?',(now()[:10],)).fetchone()[0]
            if used >= self.daily_limit: raise ApiError('Đã đạt giới hạn gọi API/ngày của ứng dụng.')
            call_id = db.execute('INSERT INTO api_calls(engine,created_at,status) VALUES(?,?,?)',
                                (params['engine'],now(),'pending')).lastrowid
        self.calls += 1
        try:
            payload = self.transport(params)
            if not isinstance(payload,dict): raise ApiError('SerpApi trả dữ liệu không hợp lệ.')
            if payload.get('error'):
                raise ApiError('SerpApi báo lỗi truy vấn. Kiểm tra hạn mức và truy vấn trên dashboard.')
            if payload.get('search_metadata',{}).get('status') in {'Processing','Queued'}:
                raise ApiError('Kết quả API chưa sẵn sàng. Thử lại sau.')
            if params['engine']=='google_maps' and 'local_results' not in payload:
                # Explicit empty-result state is valid; other schemas are not silently treated as empty.
                state=payload.get('search_information',{}).get('local_results_state','')
                if 'no results' not in state.lower(): raise ApiError('Không nhận được danh sách nhà hàng từ API.')
                payload['local_results']=[]
            if params['engine']=='google_maps_reviews' and 'reviews' not in payload:
                if payload.get('place_info',{}).get('reviews')==0: payload['reviews']=[]
                else: raise ApiError('Không nhận được review từ API.')
            payload = sanitize(payload,self.key)
            stamp = now()
            with self.store.connect() as db:
                db.execute('INSERT OR REPLACE INTO api_cache VALUES(?,?,?)',(cache_key,encode(payload),stamp))
                db.execute('UPDATE api_calls SET status=? WHERE id=?',('success',call_id))
            return payload,stamp
        except Exception:
            with self.store.connect() as db:
                db.execute('UPDATE api_calls SET status=? WHERE id=?',('failed',call_id))
            raise

def number(value):
    try:
        value=float(value)
        return value if 1<=value<=5 else None
    except (ValueError,TypeError): return None

def iso_date(value):
    if not isinstance(value,str): return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None: return None
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError: return None

def save_restaurant(store, row, stamp):
    rid = row.get('data_id') or row.get('place_id')
    if not row.get('title'): return None
    identity=normalize_name(row['title'])+'|'+normalize_name(row.get('address',''))
    if not rid:
        if not normalize_name(row.get('address','')): return None
        rid='fallback:'+hashlib.sha256(identity.encode()).hexdigest()[:24]
    with store.connect() as db:
        for old in db.execute('SELECT id,name,address FROM restaurants'):
            if normalize_name(old['name'])+'|'+normalize_name(old['address'])==identity:
                rid=old['id'];break
    # Never build an outgoing server request using a provider-supplied URL.
    link = 'https://www.google.com/maps/search/?api=1&query='+urllib.parse.quote(row['title'])
    if row.get('place_id'): link += '&query_place_id='+urllib.parse.quote(row['place_id'])
    count = row.get('reviews')
    count = count if isinstance(count,int) and count>=0 else None
    item={'id':rid,'name':row['title'],'address':row.get('address',''), 'rating':number(row.get('rating')),
          'total_reviews':count,'price':row.get('price',''),'category':row.get('type',''),
          'source_url':link,'fetched_at':stamp,'payload':encode(row)}
    with store.connect() as db:
        db.execute('''INSERT INTO restaurants VALUES(:id,:name,:address,:rating,:total_reviews,:price,:category,:source_url,:fetched_at,:payload)
        ON CONFLICT(id) DO UPDATE SET name=excluded.name,address=excluded.address,rating=excluded.rating,
        total_reviews=excluded.total_reviews,price=excluded.price,category=excluded.category,
        source_url=excluded.source_url,fetched_at=excluded.fetched_at,payload=excluded.payload''',item)
    return item

def save_reviews(store, restaurant_id, rows, stamp):
    with store.connect() as db:
        for row in rows:
            text = row.get('snippet') or ''
            if not isinstance(text,str): text=''
            rid = row.get('review_id') or row.get('link')
            if not rid:
                rid=hashlib.sha256(encode([text,row.get('rating'),row.get('iso_date'),row.get('user',{}).get('contributor_id')]).encode()).hexdigest()
            old=db.execute('SELECT text FROM reviews WHERE restaurant_id=? AND id=?',(restaurant_id,rid)).fetchone()
            if old and old['text'] != text:
                db.execute('DELETE FROM analyses WHERE restaurant_id=? AND review_id=?',(restaurant_id,rid))
            db.execute('''INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?)
              ON CONFLICT(restaurant_id,id) DO UPDATE SET text=excluded.text,rating=excluded.rating,
              published_at=excluded.published_at,date_text=excluded.date_text,source_url=excluded.source_url,
              fetched_at=excluded.fetched_at,payload=excluded.payload''',
              (restaurant_id,rid,text,number(row.get('rating')),iso_date(row.get('iso_date')),
               row.get('date',''),safe_url(row.get('link','')),stamp,encode(sanitize(row))))

class Analyzer:
    def __init__(self, model_path):
        self.bundle=None
        self.version='rating-only'
        path=Path(model_path)
        if path.exists():
            import joblib
            self.bundle=joblib.load(path) # Trusted local training output only.
            self.version='svm-'+hashlib.sha256(path.read_bytes()).hexdigest()[:12]

    def assess(self, store, restaurant_id):
        with store.connect() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM reviews WHERE restaurant_id=? ORDER BY published_at DESC',(restaurant_id,))]
        counts={a:Counter() for a in ASPECTS}
        evidence=[]
        for r in rows:
            labels=[]
            if self.bundle and r['text'].strip():
                digest=hashlib.sha256(r['text'].encode()).hexdigest()
                with store.connect() as db:
                    cached=db.execute('SELECT labels FROM analyses WHERE restaurant_id=? AND review_id=? AND model_version=? AND text_hash=?',
                                      (restaurant_id,r['id'],self.version,digest)).fetchone()
                if cached: labels=json.loads(cached['labels'])
                else:
                    pred=self.bundle['model'].predict(self.bundle['vectorizer'].transform([normalize(r['text'])]))[0]
                    labels=[c for c,v in zip(self.bundle['classes'],pred) if v]
                    with store.connect() as db:
                        db.execute('INSERT OR REPLACE INTO analyses VALUES(?,?,?,?,?,?)',
                                   (restaurant_id,r['id'],self.version,digest,encode(labels),now()))
                for label in labels:
                    aspect,polarity=label.split(':')
                    counts[aspect][polarity]+=1
            evidence.append({'id':r['id'],'text':r['text'],'rating':r['rating'],
                'published_at':r['published_at'],'date_text':r['date_text'],'source_url':r['source_url'],'labels':labels})
        stars=[r['rating'] for r in rows if r['rating'] is not None]
        monthly=defaultdict(list)
        for r in rows:
            if r['published_at'] and r['rating'] is not None: monthly[r['published_at'][:7]].append(r['rating'])
        months=[{'month':m,'count':len(v),'rating':round(sum(v)/len(v),2)} for m,v in sorted(monthly.items())]
        summary=[]
        if stars:
            summary.append(f'Trong mẫu {len(stars)} review có điểm sao, {sum(v>=4 for v in stars)} review đạt 4–5 sao và {sum(v<=2 for v in stars)} review đạt 1–2 sao.')
        if self.bundle:
            names={'food':'món ăn','price':'giá cả','service':'phục vụ','ambience':'không gian','location':'vị trí'}
            for a,c in counts.items():
                if c['POSITIVE'] or c['NEGATIVE']:
                    summary.append(f"Về {names[a]}, mô hình dự đoán {c['POSITIVE']} review tích cực và {c['NEGATIVE']} review tiêu cực.")
        if not summary: summary=['Chưa có đủ bằng chứng để đưa ra nhận xét.']
        return {'model':self.version,'n':len(rows),'n_text':sum(bool(r['text'].strip()) for r in rows),
                'sample_rating':round(sum(stars)/len(stars),2) if stars else None,
                'aspects':{a:dict(c) for a,c in counts.items()},'evidence':evidence,'months':months,'summary':' '.join(summary),
                'has_trend_sample':sum(m['count']>=3 for m in months)>=2,
                'last_fetched':max((r['fetched_at'] for r in rows),default=None)}

def search_area(store, client, analyzer, area, cuisine='', limit=3, pages=1, place=None):
    if not 1<=limit<=20 or not 1<=pages<=10: raise ValueError('Giới hạn truy vấn không hợp lệ.')
    query='nhà hàng '+cuisine.strip()+' tại '+' '.join(area.split())
    payload,stamp=client.fetch({'engine':'google_maps','type':'search','q':query,'hl':'vi','gl':'vn'})
    results=[]; warnings=[]; seen=set()
    for raw in payload['local_results']:
        if len(results)>=limit: break
        if place and place['level']=='ward':
            # Maps searches include nearby businesses. Never attach those to
            # the requested ward merely because they appeared in its results.
            ward=normalize_name(place['name'].split(' ',1)[-1])
            address=normalize_name(raw.get('address',''))
            parts=[normalize_name(part) for part in raw.get('address','').split(',')]
            if not ward or not any(part in {ward, 'phuong '+ward, 'xa '+ward}
                                   for part in parts) or 'da nang' not in address:
                continue
        item=save_restaurant(store,raw,stamp)
        if not item: continue
        rid=item['id']
        if rid in seen: continue
        seen.add(rid)
        provider_id=raw.get('data_id') or raw.get('place_id')
        if not provider_id:
            warnings.append(item['name']+': không có ID nguồn để lấy review.')
            item.pop('payload')
            item.update(assessment=analyzer.assess(store,rid),review_error='Không có ID nguồn',pages_fetched=0)
            results.append(item)
            continue
        params={'engine':'google_maps_reviews','hl':'vi','sort_by':'newestFirst'}
        params['data_id' if raw.get('data_id') else 'place_id']=provider_id
        tokens=set(); error=None; pages_fetched=0
        for _ in range(pages):
            try:
                response,review_stamp=client.fetch(params)
                save_reviews(store,rid,response['reviews'],review_stamp)
                pages_fetched+=1
                token=response.get('serpapi_pagination',{}).get('next_page_token')
                if not token or token in tokens: break
                tokens.add(token)
                params={**params,'next_page_token':token,'num':20}
            except ApiError as e:
                error=str(e);warnings.append(item['name']+': '+error);break
        item.pop('payload')
        item.update(assessment=analyzer.assess(store,rid),review_error=error,pages_fetched=pages_fetched)
        results.append(item)
    result={'restaurants':results,'warnings':warnings,'calls':client.calls,'cache_hits':client.hits,
            'listing_fetched_at':stamp,'requested_limit':limit,'pages_per_restaurant':pages}
    with store.connect() as db:
        sid=db.execute('INSERT INTO searches(area,query,created_at,status,result) VALUES(?,?,?,?,?)',
                       (area,query,now(),'partial' if warnings else 'success',encode(result))).lastrowid
    return sid
