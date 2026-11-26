"""Enrich under-covered Da Nang wards within a measured SerpApi budget.

The primary database is persistent; rerunning skips wards that already have
enough distinct restaurants and saved source reviews. No model labels are
invented during ingestion.
"""
import argparse
import json
import os
import urllib.request
from urllib.parse import urlencode

from dotenv import load_dotenv

from assistant_service import crawl_or_reuse
from locations import place
from restaurant_service import Analyzer, ApiError, SerpClient
from storage import Store


DEFAULT_WARDS = (14, 13, 4, 10, 12, 6, 11, 23, 24, 25)


def coverage(store, location_id):
    with store.connect() as db:
        row = db.execute('''SELECT COUNT(DISTINCT r.id) restaurants,
            COUNT(v.id) reviews FROM restaurant_locations l
            JOIN restaurants r ON r.id=l.restaurant_id
            LEFT JOIN reviews v ON v.restaurant_id=r.id
            WHERE l.location_id=?''', (location_id,)).fetchone()
    return dict(row)


def account_remaining(key):
    # SerpApi documents that Account API calls do not consume search quota.
    url = 'https://serpapi.com/account.json?' + urlencode({'api_key': key})
    with urllib.request.urlopen(url, timeout=20) as response:
        account = json.load(response)
    remaining = account.get('total_searches_left')
    if not isinstance(remaining, int):
        raise RuntimeError('Unable to verify remaining SerpApi searches.')
    return remaining


def enrich(store, key, budget=200, ward_ids=DEFAULT_WARDS, min_restaurants=3,
           min_reviews=60, per_ward=7, pages=2):
    if not 1 <= budget <= 200:
        raise ValueError('The per-run request budget must be between 1 and 200.')
    remaining = account_remaining(key)
    if remaining < 2:
        raise RuntimeError('Insufficient confirmed SerpApi quota.')
    with store.connect() as db:
        used_today = db.execute("SELECT COUNT(*) FROM api_calls WHERE created_at>=date('now')").fetchone()[0]
    allowed = min(budget, remaining - 1)  # leave at least one account credit
    client = SerpClient(store, key=key, daily_limit=used_today + allowed)
    analyzer = Analyzer('outputs/baseline.joblib')
    results = []
    for location_id in ward_ids:
        location = place(store, location_id)
        if not location or location['level'] != 'ward':
            raise ValueError(f'Invalid ward ID: {location_id}')
        before = coverage(store, location_id)
        item = {'id': location_id, 'name': location['name'], 'before': before}
        if before['restaurants'] >= min_restaurants and before['reviews'] >= min_reviews:
            item['status'] = 'covered'; results.append(item); continue
        # A listing request plus `pages` review requests per candidate is the
        # worst case. Stop before the next ward would exceed this run's cap.
        if client.calls + 1 + per_ward * pages > allowed:
            item['status'] = 'budget_reserved'; results.append(item); break
        cuisine = 'hải sản' if location_id == 14 else ''
        try:
            _, reused = crawl_or_reuse(store, client, analyzer, location,
                                       cuisine=cuisine, limit=per_ward, pages=pages)
            item['status'] = 'reused' if reused else 'enriched'
        except ApiError as exc:
            item['status'] = 'api_error'; item['error'] = str(exc)
            results.append(item)
            break
        item['after'] = coverage(store, location_id)
        results.append(item)
        print(json.dumps({'progress': item, 'requests': client.calls}, ensure_ascii=True), flush=True)
    return {'budget': budget, 'account_remaining_at_start': remaining,
            'requests': client.calls, 'local_cache_hits': client.hits, 'wards': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='instance/food_reviews.sqlite3')
    parser.add_argument('--budget', type=int, default=200)
    parser.add_argument('--wards', type=int, nargs='*', default=DEFAULT_WARDS)
    parser.add_argument('--restaurants', type=int, default=7)
    parser.add_argument('--pages', type=int, default=2)
    args = parser.parse_args()
    load_dotenv('.env')
    key = os.getenv('SERPAPI_API_KEY', '').strip()
    if not key:
        parser.error('SERPAPI_API_KEY is missing.')
    report = enrich(Store(args.db), key, args.budget, args.wards,
                    per_ward=args.restaurants, pages=args.pages)
    print(json.dumps(report, ensure_ascii=True, indent=2))
