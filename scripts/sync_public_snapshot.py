"""Update the public demo's review data while preserving its own accounts.

Run while the public web worker is stopped. A backup is kept beside the demo
database. Private users, conversations, API logs, and annotation records from
the local database are never copied.
"""
import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from data_pipeline import build_index
from storage import Store


PUBLIC_FIELDS = {'serpapi_thumbnail', 'gps_coordinates', 'data_id', 'place_id', 'provider_id'}
DATA_TABLES = ('locations', 'location_aliases', 'restaurants', 'reviews', 'analyses',
               'restaurant_locations', 'monthly_trends', 'period_aggregates', 'trend_signals')


def sync(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or not source.is_file() or not target.is_file():
        raise ValueError('Source and existing public target must be different database files.')
    backup = target.with_name(target.stem + '_before_enrichment.sqlite3')
    stage = target.with_name(target.stem + '_staged.sqlite3')
    if backup.exists() or stage.exists():
        raise FileExistsError('Backup or staging database already exists; inspect it first.')
    with closing(sqlite3.connect(target)) as old, closing(sqlite3.connect(backup)) as copy:
        old.backup(copy)
    with closing(sqlite3.connect(backup)) as old, closing(sqlite3.connect(stage)) as copy:
        old.backup(copy)
    with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(stage)) as demo:
        demo.execute('PRAGMA foreign_keys=OFF')
        for table in DATA_TABLES:
            rows = original.execute(f'SELECT * FROM "{table}"').fetchall()
            if table == 'restaurants':
                clean = []
                for row in rows:
                    try: payload = json.loads(row[-1])
                    except (ValueError, TypeError): payload = {}
                    clean.append((*row[:-1], json.dumps({k: payload[k] for k in PUBLIC_FIELDS
                                                        if k in payload}, ensure_ascii=False)))
                rows = clean
            elif table == 'reviews':
                rows = [(*row[:-1], '{}') for row in rows]
            if rows:
                placeholders = ','.join('?' for _ in rows[0])
                demo.executemany(f'INSERT OR REPLACE INTO "{table}" VALUES({placeholders})', rows)
        demo.commit()
    indexed = build_index(Store(stage))
    with closing(sqlite3.connect(stage)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('The staged public database failed integrity check.')
        counts = {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                  for table in ('restaurants', 'reviews', 'accounts', 'review_documents')}
    stage.replace(target)
    return {'counts': counts, 'index': indexed, 'backup': str(backup)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='instance/food_reviews.sqlite3')
    parser.add_argument('--target', default='instance/demo_tunnel.sqlite3')
    args = parser.parse_args()
    print(json.dumps(sync(args.source, args.target), ensure_ascii=True))
