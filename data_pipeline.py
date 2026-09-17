"""Incremental SerpApi -> SQLite -> ABSA -> trend baseline -> BM25 pipeline."""
import argparse
import hashlib
import json
import os
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from restaurant_service import Analyzer, ApiError, SerpClient, encode, now, save_restaurant, save_reviews
from storage import Store

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / 'instance' / 'food_reviews.sqlite3'
DEFAULT_MODEL = ROOT / 'outputs' / 'baseline.joblib'
ASPECTS = ['food', 'price', 'service', 'ambience', 'location']


def json_print(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def start_job(store, job_type, parameters):
    with store.connect() as db:
        return db.execute('''INSERT INTO pipeline_jobs(job_type,parameters,status,started_at)
            VALUES(?,?,?,?)''', (job_type, encode(parameters), 'running', now())).lastrowid


def finish_job(store, job_id, status, stats=None, error=''):
    with store.connect() as db:
        db.execute('''UPDATE pipeline_jobs SET status=?,finished_at=?,stats=?,error=? WHERE id=?''',
                   (status, now(), encode(stats or {}), str(error)[:1000], job_id))


def add_seed(store, area, cuisine=''):
    area = ' '.join(area.split())
    cuisine = ' '.join(cuisine.split())
    if not 2 <= len(area) <= 160 or len(cuisine) > 80:
        raise ValueError('Khu vực hoặc loại món không hợp lệ.')
    with store.connect() as db:
        db.execute('''INSERT INTO ingestion_seeds(area,cuisine,enabled) VALUES(?,?,1)
            ON CONFLICT(area,cuisine) DO UPDATE SET enabled=1''', (area, cuisine))
    return {'area': area, 'cuisine': cuisine, 'enabled': True}


def ingest_restaurants(store, client, area, cuisine='', limit=20):
    if not 1 <= limit <= 20:
        raise ValueError('limit phải từ 1 đến 20.')
    params = {'engine': 'google_maps', 'type': 'search',
              'q': f"nhà hàng {cuisine.strip()} tại {' '.join(area.split())}", 'hl': 'vi', 'gl': 'vn'}
    payload, stamp = client.fetch(params)
    inserted = updated = skipped = 0
    seen = set()
    with store.connect() as db:
        existing = {r[0] for r in db.execute('SELECT id FROM restaurants')}
    for raw in payload.get('local_results', []):
        if inserted + updated >= limit:
            break
        rid = raw.get('data_id') or raw.get('place_id')
        if not rid or rid in seen:
            skipped += 1
            continue
        seen.add(rid)
        item = save_restaurant(store, raw, stamp)
        if not item:
            skipped += 1
            continue
        inserted += int(rid not in existing)
        updated += int(rid in existing)
        with store.connect() as db:
            db.execute('''INSERT OR IGNORE INTO restaurant_crawl_state(restaurant_id,status)
                VALUES(?, 'pending')''', (rid,))
    with store.connect() as db:
        db.execute('''INSERT INTO ingestion_seeds(area,cuisine,enabled,last_run_at) VALUES(?,?,1,?)
            ON CONFLICT(area,cuisine) DO UPDATE SET last_run_at=excluded.last_run_at,enabled=1''',
                   (' '.join(area.split()), ' '.join(cuisine.split()), now()))
    return {'inserted': inserted, 'updated': updated, 'skipped': skipped,
            'api_calls': client.calls, 'cache_hits': client.hits}


def ingest_seeds(store, client, max_seeds=5, per_seed_limit=20):
    if not 1 <= max_seeds <= 100:
        raise ValueError('max-seeds phải từ 1 đến 100.')
    with store.connect() as db:
        seeds = [dict(r) for r in db.execute('''SELECT area,cuisine FROM ingestion_seeds
            WHERE enabled=1 ORDER BY COALESCE(last_run_at,''),id LIMIT ?''', (max_seeds,))]
    results=[]
    for seed in seeds:
        try:
            result=ingest_restaurants(store,client,seed['area'],seed['cuisine'],per_seed_limit)
            results.append({**seed,**result,'status':'success'})
        except ApiError as exc:
            results.append({**seed,'status':'stopped','error':str(exc)})
            break
    return {'seeds_attempted':len(results),'results':results,'api_calls':client.calls,
            'cache_hits':client.hits,'stopped_early':bool(results and results[-1]['status']=='stopped')}


def _crawl_candidates(store, maximum, refresh):
    with store.connect() as db:
        if refresh:
            rows = db.execute('''SELECT r.id,r.payload,s.next_page_token,s.status FROM restaurants r
                LEFT JOIN restaurant_crawl_state s ON s.restaurant_id=r.id
                ORDER BY COALESCE(s.last_attempt_at,'') LIMIT ?''', (maximum,)).fetchall()
        else:
            rows = db.execute('''SELECT r.id,r.payload,s.next_page_token,s.status FROM restaurants r
                LEFT JOIN restaurant_crawl_state s ON s.restaurant_id=r.id
                WHERE s.status IS NULL OR s.status IN ('pending','error','running')
                ORDER BY COALESCE(s.last_attempt_at,'') LIMIT ?''', (maximum,)).fetchall()
        return [dict(r) for r in rows]


def ingest_reviews(store, client, max_restaurants=20, pages=1, refresh=False):
    if not 1 <= max_restaurants <= 100 or not 1 <= pages <= 10:
        raise ValueError('Giới hạn restaurant/pages không hợp lệ.')
    stats = {'restaurants_attempted': 0, 'restaurants_complete': 0, 'pages': 0,
             'reviews_received': 0, 'errors': 0, 'api_calls': 0, 'cache_hits': 0}
    for candidate in _crawl_candidates(store, max_restaurants, refresh):
        rid = candidate['id']; token = None if refresh else candidate.get('next_page_token')
        raw = json.loads(candidate.get('payload') or '{}')
        identifier = ('data_id', raw['data_id']) if raw.get('data_id') else ('place_id', raw.get('place_id') or rid)
        stats['restaurants_attempted'] += 1
        with store.connect() as db:
            db.execute('''INSERT INTO restaurant_crawl_state(restaurant_id,status,last_attempt_at)
                VALUES(?, 'running', ?) ON CONFLICT(restaurant_id) DO UPDATE SET
                status='running',last_attempt_at=excluded.last_attempt_at,error='' ''', (rid, now()))
        try:
            complete = False
            for page_no in range(pages):
                params = {'engine': 'google_maps_reviews', 'hl': 'vi', 'sort_by': 'newestFirst',
                          identifier[0]: identifier[1]}
                if token:
                    params.update(next_page_token=token, num=20)
                response, stamp = client.fetch(params)
                rows = response.get('reviews', [])
                save_reviews(store, rid, rows, stamp)
                stats['pages'] += 1; stats['reviews_received'] += len(rows)
                next_token = response.get('serpapi_pagination', {}).get('next_page_token')
                complete = not next_token or next_token == token
                token = None if complete else next_token
                with store.connect() as db:
                    db.execute('''UPDATE restaurant_crawl_state SET next_page_token=?,pages_fetched=pages_fetched+1,
                        review_requests=review_requests+1,last_success_at=?,status=?,error='' WHERE restaurant_id=?''',
                               (token, now(), 'complete' if complete else 'pending', rid))
                if complete:
                    break
            stats['restaurants_complete'] += int(complete)
        except ApiError as exc:
            stats['errors'] += 1
            with store.connect() as db:
                db.execute('''UPDATE restaurant_crawl_state SET status='error',error=?,last_attempt_at=?
                    WHERE restaurant_id=?''', (str(exc)[:500], now(), rid))
    stats['api_calls'] = client.calls; stats['cache_hits'] = client.hits
    return stats


def analyze_pending(store, analyzer, limit=1000):
    if analyzer.bundle is None:
        raise ValueError('Chưa có outputs/baseline.joblib. Chạy train_model.bat trước.')
    with store.connect() as db:
        rows = db.execute('''SELECT r.restaurant_id,r.id,r.text FROM reviews r
            LEFT JOIN analyses a ON a.restaurant_id=r.restaurant_id AND a.review_id=r.id
                AND a.model_version=?
            WHERE a.review_id IS NULL AND trim(r.text)<>'' ORDER BY r.fetched_at,r.restaurant_id,r.id LIMIT ?''',
            (analyzer.version, limit)).fetchall()
    if not rows:
        return {'analyzed': 0, 'model_version': analyzer.version}
    texts = [r['text'] for r in rows]
    normalized = [__import__('pipeline').normalize(t) for t in texts]
    predictions = analyzer.bundle['model'].predict(analyzer.bundle['vectorizer'].transform(normalized))
    stamp = now()
    with store.connect() as db:
        for row, pred in zip(rows, predictions):
            labels = [c for c, value in zip(analyzer.bundle['classes'], pred) if value]
            db.execute('''INSERT OR REPLACE INTO analyses
                (restaurant_id,review_id,model_version,text_hash,labels,created_at) VALUES(?,?,?,?,?,?)''',
                (row['restaurant_id'], row['id'], analyzer.version,
                 hashlib.sha256(row['text'].encode()).hexdigest(), encode(labels), stamp))
    return {'analyzed': len(rows), 'model_version': analyzer.version}


def compute_trends(store, model_version=None):
    with store.connect() as db:
        if model_version is None:
            row = db.execute('SELECT model_version,COUNT(*) n FROM analyses GROUP BY model_version ORDER BY n DESC LIMIT 1').fetchone()
            model_version = row['model_version'] if row else 'rating-only'
        rows = db.execute('''SELECT r.restaurant_id,r.id,r.published_at,r.rating,a.labels
            FROM reviews r LEFT JOIN analyses a ON a.restaurant_id=r.restaurant_id
                AND a.review_id=r.id AND a.model_version=?
            WHERE r.published_at IS NOT NULL''', (model_version,)).fetchall()
    grouped = defaultdict(lambda: {'reviews': set(), 'ratings': [], 'polarity': Counter()})
    for row in rows:
        month = row['published_at'][:7]
        labels = json.loads(row['labels']) if row['labels'] else []
        for aspect in ASPECTS:
            bucket = grouped[(row['restaurant_id'], month, aspect)]
            bucket['reviews'].add(row['id'])
            if row['rating'] is not None:
                bucket['ratings'].append(row['rating'])
        for label in labels:
            aspect, polarity = label.split(':', 1)
            grouped[(row['restaurant_id'], month, aspect)]['polarity'][polarity] += 1
    with store.connect() as db:
        db.execute('DELETE FROM monthly_trends WHERE model_version=?', (model_version,))
        for (rid, month, aspect), value in grouped.items():
            ratings = value['ratings']; p = value['polarity']
            db.execute('''INSERT INTO monthly_trends VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (rid, month, aspect, len(value['reviews']), p['POSITIVE'], p['NEUTRAL'], p['NEGATIVE'],
                 round(sum(ratings)/len(ratings), 3) if ratings else None, model_version, now()))
        trend_rows=db.execute('''SELECT * FROM monthly_trends WHERE model_version=?
            ORDER BY restaurant_id,aspect,month''',(model_version,)).fetchall()
        db.execute('DELETE FROM trend_signals WHERE model_version=?',(model_version,))
        series=defaultdict(list)
        for row in trend_rows: series[(row['restaurant_id'],row['aspect'])].append(dict(row))
        signal_count=0
        for (rid,aspect),items in series.items():
            ratings=[];previous=None
            for item in items:
                if item['average_rating'] is not None: ratings.append(item['average_rating'])
                mentions=item['positive_count']+item['neutral_count']+item['negative_count']
                sentiment=(item['positive_count']-item['negative_count'])/mentions if mentions else None
                volume_change=item['review_count']-previous['review_count'] if previous else None
                rating_change=(item['average_rating']-previous['average_rating']) if previous and item['average_rating'] is not None and previous['average_rating'] is not None else None
                previous_mentions=(previous['positive_count']+previous['neutral_count']+previous['negative_count']) if previous else 0
                previous_sentiment=(previous['positive_count']-previous['negative_count'])/previous_mentions if previous_mentions else None
                sentiment_shift=sentiment-previous_sentiment if sentiment is not None and previous_sentiment is not None else None
                moving=round(sum(ratings[-3:])/len(ratings[-3:]),3) if ratings else None
                enough=len(items)>=2 and item['review_count']>=3
                volume_norm=(volume_change/max(previous['review_count'],1)) if previous and volume_change is not None else 0
                score=.35*max(-1,min(1,volume_norm))+.4*(sentiment_shift or 0)+.25*((rating_change or 0)/4)
                score=round(max(-1,min(1,score)),3)
                level='insufficient' if not enough else ('strong' if abs(score)>=.5 else 'weak' if abs(score)>=.25 else 'stable')
                db.execute('''INSERT INTO trend_signals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (rid,item['month'],aspect,item['review_count'],volume_change,item['average_rating'],
                     round(rating_change,3) if rating_change is not None else None,moving,
                     round(sentiment,3) if sentiment is not None else None,
                     round(sentiment_shift,3) if sentiment_shift is not None else None,
                     score,level,int(enough),model_version,now()))
                signal_count+=1;previous=item
    return {'monthly_rows': len(grouped), 'trend_signal_rows':signal_count,
            'dated_reviews': len({(r['restaurant_id'],r['id']) for r in rows}),
            'model_version': model_version, 'claim': 'retrospective-baseline-not-BERTrend'}


def data_report(store, output_dir=ROOT/'outputs'):
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    with store.connect() as db:
        summary=status(store)
        ratings={str(r['rating']):r['n'] for r in db.execute(
            'SELECT rating,COUNT(*) n FROM reviews GROUP BY rating ORDER BY rating')}
        categories=[dict(r) for r in db.execute('''SELECT COALESCE(NULLIF(category,''),'Unknown') category,
            COUNT(*) restaurants FROM restaurants GROUP BY category ORDER BY restaurants DESC''')]
        months=[dict(r) for r in db.execute('''SELECT substr(published_at,1,7) month,COUNT(*) reviews,
            COUNT(DISTINCT restaurant_id) restaurants FROM reviews WHERE published_at IS NOT NULL
            GROUP BY month ORDER BY month''')]
        labels=Counter()
        for row in db.execute('SELECT labels FROM analyses'):
            labels.update(json.loads(row['labels']))
    card={'generated_at':now(),'source':'SerpApi Google Maps','summary':summary,
          'rating_distribution':ratings,'restaurant_categories':categories,
          'monthly_coverage':months,'predicted_label_distribution':dict(labels),
          'limitations':['SerpApi snapshot is not a probability sample.',
            'ABSA labels are model predictions, not manual ground truth.',
            'Only source-provided ISO timestamps are used for temporal analysis.']}
    (output_dir/'data_card.json').write_text(json.dumps(card,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# FoodLens data card','',f"Generated: {card['generated_at']}",'',
           '## Coverage','',f"- Restaurants: {summary['restaurants']}",f"- Reviews: {summary['reviews']}",
           f"- Dated reviews: {summary['dated_reviews']}",f"- Distinct months: {summary['coverage']['distinct_months']}",
           f"- Date range: {summary['coverage']['min_date']} to {summary['coverage']['max_date']}",'',
           '## Limitations','']+[f'- {x}' for x in card['limitations']]
    (output_dir/'data_card.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with (output_dir/'data_quality.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['metric','value'])
        for key in ['restaurants','reviews','dated_reviews','pending_absa','review_documents','monthly_trends']:
            writer.writerow([key,summary[key]])
    return {'json':str(output_dir/'data_card.json'),'markdown':str(output_dir/'data_card.md'),
            'csv':str(output_dir/'data_quality.csv'),'summary':summary}


def build_index(store, model_version=None):
    with store.connect() as db:
        if model_version is None:
            row = db.execute('SELECT model_version,COUNT(*) n FROM analyses GROUP BY model_version ORDER BY n DESC LIMIT 1').fetchone()
            model_version = row['model_version'] if row else 'rating-only'
        rows = db.execute('''SELECT rv.restaurant_id,rv.id,rv.text,rv.rating,rv.published_at,rv.source_url,
                r.name,r.category,a.labels FROM reviews rv JOIN restaurants r ON r.id=rv.restaurant_id
                LEFT JOIN analyses a ON a.restaurant_id=rv.restaurant_id AND a.review_id=rv.id
                    AND a.model_version=? WHERE trim(rv.text)<>'' ''', (model_version,)).fetchall()
        db.execute('DELETE FROM review_fts'); db.execute('DELETE FROM review_documents')
        for row in rows:
            key = row['restaurant_id'] + ':' + row['id']
            metadata = {'restaurant_id': row['restaurant_id'], 'review_id': row['id'],
                'rating': row['rating'], 'published_at': row['published_at'], 'source_url': row['source_url'],
                'labels': json.loads(row['labels']) if row['labels'] else [], 'model_version': model_version}
            db.execute('INSERT INTO review_documents VALUES(?,?,?,?,?,?,?,?)',
                (key,row['restaurant_id'],row['id'],row['text'],row['name'],row['category'],encode(metadata),now()))
            db.execute('INSERT INTO review_fts(document_key,text,restaurant_name,category) VALUES(?,?,?,?)',
                (key,row['text'],row['name'],row['category']))
    return {'indexed': len(rows), 'index': 'SQLite FTS5 BM25', 'model_version': model_version}


def search_index(store, query, limit=5):
    if not query.strip() or not 1 <= limit <= 20:
        raise ValueError('Query/limit không hợp lệ.')
    with store.connect() as db:
        rows = db.execute('''SELECT d.*,bm25(review_fts) score FROM review_fts
            JOIN review_documents d USING(document_key) WHERE review_fts MATCH ?
            ORDER BY score LIMIT ?''', (query, limit)).fetchall()
    return [{**dict(r), 'metadata': json.loads(r['metadata_json'])} for r in rows]


def snapshot(store, notes=''):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    with store.connect() as db:
        values = db.execute('''SELECT (SELECT COUNT(*) FROM restaurants),
            (SELECT COUNT(*) FROM reviews),(SELECT COUNT(*) FROM reviews WHERE published_at IS NOT NULL),
            (SELECT MIN(published_at) FROM reviews),(SELECT MAX(published_at) FROM reviews)''').fetchone()
        version = 'serpapi-' + stamp
        db.execute('INSERT INTO dataset_versions VALUES(NULL,?,?,?,?,?,?,?,?,?)',
            (version, now(), values[0], values[1], values[2], values[3], values[4], 'SerpApi Google Maps', notes[:500]))
    return {'version': version, 'restaurants': values[0], 'reviews': values[1],
            'dated_reviews': values[2], 'min_date': values[3], 'max_date': values[4]}


def status(store):
    with store.connect() as db:
        counts = {name: db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in
                  ['restaurants','reviews','analyses','review_documents','monthly_trends','trend_signals','dataset_versions']}
        counts['dated_reviews'] = db.execute('SELECT COUNT(*) FROM reviews WHERE published_at IS NOT NULL').fetchone()[0]
        coverage = db.execute('''SELECT COUNT(DISTINCT restaurant_id),MIN(published_at),MAX(published_at),
            COUNT(DISTINCT substr(published_at,1,7)) FROM reviews WHERE published_at IS NOT NULL''').fetchone()
        counts['coverage'] = {'restaurants_with_dated_reviews': coverage[0], 'min_date': coverage[1],
                              'max_date': coverage[2], 'distinct_months': coverage[3]}
        counts['pending_absa'] = db.execute('''SELECT COUNT(*) FROM reviews r WHERE trim(r.text)<>'' AND NOT EXISTS
            (SELECT 1 FROM analyses a WHERE a.restaurant_id=r.restaurant_id AND a.review_id=r.id)''').fetchone()[0]
        counts['crawl_states'] = {r['status']: r['n'] for r in db.execute(
            'SELECT status,COUNT(*) n FROM restaurant_crawl_state GROUP BY status')}
        counts['recent_jobs'] = [dict(r) for r in db.execute(
            'SELECT id,job_type,status,started_at,finished_at,error FROM pipeline_jobs ORDER BY id DESC LIMIT 10')]
    return counts


def main(argv=None):
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser(description='FoodLens incremental data pipeline')
    parser.add_argument('--db', default=str(DEFAULT_DB))
    parser.add_argument('--model', default=str(DEFAULT_MODEL))
    parser.add_argument('--daily-limit', type=int, default=int(os.getenv('SERPAPI_DAILY_LIMIT','30')))
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('seed'); p.add_argument('--area', required=True); p.add_argument('--cuisine', default='')
    p = sub.add_parser('ingest-restaurants'); p.add_argument('--area', required=True); p.add_argument('--cuisine', default=''); p.add_argument('--limit', type=int, default=20)
    p = sub.add_parser('ingest-seeds'); p.add_argument('--max-seeds',type=int,default=5); p.add_argument('--per-seed-limit',type=int,default=20)
    p = sub.add_parser('ingest-reviews'); p.add_argument('--max-restaurants', type=int, default=20); p.add_argument('--pages', type=int, default=1); p.add_argument('--refresh', action='store_true')
    p = sub.add_parser('analyze-pending'); p.add_argument('--limit', type=int, default=1000)
    p = sub.add_parser('compute-trends'); p.add_argument('--model-version')
    p = sub.add_parser('build-index'); p.add_argument('--model-version')
    p = sub.add_parser('search-index'); p.add_argument('query'); p.add_argument('--limit', type=int, default=5)
    p = sub.add_parser('snapshot'); p.add_argument('--notes', default='')
    p = sub.add_parser('data-report'); p.add_argument('--output-dir',default=str(ROOT/'outputs'))
    sub.add_parser('status')
    args = parser.parse_args(argv); store = Store(args.db)
    if args.command == 'status': result = status(store)
    elif args.command == 'seed': result = add_seed(store,args.area,args.cuisine)
    elif args.command == 'search-index': result = search_index(store,args.query,args.limit)
    elif args.command == 'snapshot': result = snapshot(store,args.notes)
    elif args.command == 'data-report': result = data_report(store,args.output_dir)
    else:
        params = vars(args).copy(); params.pop('db'); params.pop('model'); job_id = start_job(store,args.command,params)
        try:
            if args.command == 'ingest-restaurants':
                result = ingest_restaurants(store,SerpClient(store,daily_limit=args.daily_limit),args.area,args.cuisine,args.limit)
            elif args.command == 'ingest-seeds':
                result = ingest_seeds(store,SerpClient(store,daily_limit=args.daily_limit),args.max_seeds,args.per_seed_limit)
            elif args.command == 'ingest-reviews':
                result = ingest_reviews(store,SerpClient(store,daily_limit=args.daily_limit),args.max_restaurants,args.pages,args.refresh)
            elif args.command == 'analyze-pending': result = analyze_pending(store,Analyzer(args.model),args.limit)
            elif args.command == 'compute-trends': result = compute_trends(store,args.model_version)
            elif args.command == 'build-index': result = build_index(store,args.model_version)
            finish_job(store,job_id,'partial' if result.get('errors') else 'success',result)
        except Exception as exc:
            finish_job(store,job_id,'failed',error=str(exc)); raise
    json_print(result)
    return result


if __name__ == '__main__':
    main()
