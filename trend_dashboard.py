"""Read-only dashboard summaries from dated reviews and existing ABSA aggregates."""
from collections import defaultdict
import json
from urllib.parse import urlsplit

from assistant_view import _coordinates


def _period(date, granularity):
    return date[:{'day': 10, 'month': 7, 'year': 4}[granularity]]


def _maps_url(value):
    try:
        parsed = urlsplit(value or '')
        return value if parsed.scheme == 'https' and (
            parsed.hostname == 'google.com' or parsed.hostname == 'www.google.com'
            or parsed.hostname == 'maps.google.com'
        ) else ''
    except ValueError:
        return ''


def build_dashboard(store, granularity='month', year='all', area_id=None, aspect='food'):
    with store.connect() as db:
        restaurants = [dict(row) for row in db.execute(
            'SELECT id,name,address,source_url,payload FROM restaurants ORDER BY name')]
        placements = defaultdict(list)
        for row in db.execute('''SELECT rl.restaurant_id,l.id,l.name FROM restaurant_locations rl
            JOIN locations l ON l.id=rl.location_id WHERE l.level='ward' AND l.is_active=1'''):
            placements[row['restaurant_id']].append((row['id'], row['name']))
        reviews = [dict(row) for row in db.execute('''SELECT restaurant_id,id,published_at,rating
            FROM reviews WHERE published_at IS NOT NULL AND length(published_at)>=10''')]
        model = db.execute('''SELECT model_version,COUNT(*) n FROM analyses
            GROUP BY model_version ORDER BY n DESC LIMIT 1''').fetchone()
        aggregates = [dict(row) for row in db.execute('''SELECT restaurant_id,period,
            positive_count,neutral_count,negative_count FROM period_aggregates
            WHERE granularity=? AND aspect=? AND model_version=?''',
            (granularity, aspect, model['model_version'] if model else 'rating-only'))]

    areas = {}
    restaurant_by_id = {}
    for row in restaurants:
        mapped = placements[row['id']]
        # Ambiguous assignments stay unclassified instead of counting one quán twice.
        aid, name = mapped[0] if len(mapped) == 1 else (None, 'Chưa xác định')
        row['area_id'], row['area_name'] = aid, name
        row['location'] = _coordinates(json.loads(row['payload']))
        row['maps_url'] = _maps_url(row['source_url'])
        restaurant_by_id[row['id']] = row
        if aid is not None:
            areas.setdefault(aid, {'id': aid, 'name': name, 'restaurants': 0,
                                   'reviews': 0, 'rating_sum': 0, 'rating_n': 0,
                                   'positive': 0, 'neutral': 0, 'negative': 0})
            areas[aid]['restaurants'] += 1

    selected = [r for r in restaurants if area_id is None or r['area_id'] == area_id]
    selected_ids = {r['id'] for r in selected}
    by_restaurant = defaultdict(lambda: {'reviews': 0, 'rating_sum': 0, 'rating_n': 0})
    by_period = defaultdict(lambda: {'reviews': 0, 'rating_sum': 0, 'rating_n': 0,
                                     'positive': 0, 'neutral': 0, 'negative': 0})
    city_rating_sum = city_rating_n = 0
    city_reviews = 0
    for review in reviews:
        date = review['published_at']
        if year != 'all' and date[:4] != year:
            continue
        rid = review['restaurant_id']
        restaurant = restaurant_by_id.get(rid)
        if not restaurant:
            continue
        city_reviews += 1
        rating = review['rating']
        if rating is not None:
            city_rating_sum += rating
            city_rating_n += 1
        aid = restaurant['area_id']
        if aid in areas:
            areas[aid]['reviews'] += 1
            if rating is not None:
                areas[aid]['rating_sum'] += rating
                areas[aid]['rating_n'] += 1
        if rid not in selected_ids:
            continue
        item = by_restaurant[rid]
        item['reviews'] += 1
        period_item = by_period[_period(date, granularity)]
        period_item['reviews'] += 1
        if rating is not None:
            item['rating_sum'] += rating
            item['rating_n'] += 1
            period_item['rating_sum'] += rating
            period_item['rating_n'] += 1

    sentiment = {'positive': 0, 'neutral': 0, 'negative': 0}
    for row in aggregates:
        if year != 'all' and row['period'][:4] != year:
            continue
        restaurant = restaurant_by_id.get(row['restaurant_id'])
        if not restaurant:
            continue
        aid = restaurant['area_id']
        for key in sentiment:
            count = row[f'{key}_count']
            if aid in areas:
                areas[aid][key] += count
            if row['restaurant_id'] in selected_ids:
                sentiment[key] += count
                by_period[row['period']][key] += count

    series = [{'period': key, **value} for key, value in sorted(by_period.items())
              if value['reviews']]
    limit = {'day': 31, 'month': 24, 'year': 10}[granularity]
    clipped = len(series) > limit
    series = series[-limit:]
    maximum = max((row['reviews'] for row in series), default=0)
    for row in series:
        # Fixed steps map to stylesheet classes; CSP blocks inline style attributes.
        row['height'] = max(4, 4 * round(20 * row['reviews'] / maximum)) if maximum else 0
        mentions = sum(row[key] for key in sentiment)
        row['positive_pct'] = round(100 * row['positive'] / mentions) if mentions >= 5 else None

    city_mean = city_rating_sum / city_rating_n if city_rating_n else 0
    top = []
    for restaurant in selected:
        sample = by_restaurant[restaurant['id']]
        if sample['rating_n'] < 5:
            continue
        # Shrink small samples toward the city mean, using only fetched review ratings.
        score = (sample['rating_sum'] + 20 * city_mean) / (sample['rating_n'] + 20)
        top.append({**restaurant, 'review_count': sample['reviews'],
                    'sample_rating': round(sample['rating_sum'] / sample['rating_n'], 2),
                    'sort_score': score})
    top.sort(key=lambda row: (-row['sort_score'], -row['review_count'], row['name']))
    top = top[:5]

    area_rows = sorted(areas.values(), key=lambda row: (-row['reviews'], row['name']))
    max_area_reviews = max((row['reviews'] for row in area_rows), default=0)
    for row in area_rows:
        mentions = sum(row[key] for key in sentiment)
        row['positive_pct'] = round(100 * row['positive'] / mentions) if mentions >= 5 else None
        row['average_rating'] = round(row['rating_sum'] / row['rating_n'], 2) if row['rating_n'] else None

    reviewed = sum(row['reviews'] for row in by_restaurant.values())
    rated = sum(row['rating_n'] for row in by_restaurant.values())
    rating_sum = sum(row['rating_sum'] for row in by_restaurant.values())
    mentions = sum(sentiment.values())
    return {
        'areas': area_rows, 'max_area_reviews': max_area_reviews,
        'selected_area': area_id, 'restaurants': len(selected),
        'years': sorted({r['published_at'][:4] for r in reviews}, reverse=True),
        'reviews': reviewed, 'city_reviews': city_reviews,
        'average_rating': round(rating_sum / rated, 2) if rated else None,
        'positive_pct': round(100 * sentiment['positive'] / mentions) if mentions >= 5 else None,
        'mentions': mentions, 'series': series, 'series_clipped': clipped,
        'top': top, 'map_points': [{'id': r['id'], 'name': r['name'],
                                  'location': r['location'], 'maps_url': r['maps_url']} for r in selected
                                  if r['location'] and by_restaurant[r['id']]['reviews']],
        'model_version': model['model_version'] if model else None,
    }
