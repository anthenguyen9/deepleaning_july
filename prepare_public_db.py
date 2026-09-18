"""Make a private deployable review snapshot without local accounts or history.

The output stays under instance/ (ignored by Git). Never upload the original DB.
"""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


PRIVATE_TABLES = (
    'user_feedback', 'user_searches', 'assistant_messages', 'chat_messages',
    'chat_sessions', 'accounts', 'restaurant_feedback', 'searches', 'api_cache',
    'api_calls', 'crawl_runs', 'pipeline_jobs', 'retrieval_events',
    'evaluation_queries', 'gold_annotations',
)


def prepare(source: Path, target: Path) -> None:
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise ValueError('Source and target must differ.')
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.working.sqlite3')
    if temporary.exists():
        raise FileExistsError(temporary)
    try:
        with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(temporary)) as copy:
            original.backup(copy)
        with closing(sqlite3.connect(temporary)) as db:
            db.execute('PRAGMA foreign_keys=OFF')
            available = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for table in PRIVATE_TABLES:
                if table in available:
                    db.execute(f'DELETE FROM "{table}"')
            db.execute("UPDATE profile SET name='Người dùng', area='Đà Nẵng', cuisine='', min_rating=0, aspect='food'")
            db.execute("UPDATE preference_memory SET explicit_notes='', learned_summary=''")
            db.execute("UPDATE restaurants SET payload='{}'")
            db.execute("UPDATE reviews SET payload='{}'")
            db.commit()
            db.execute('VACUUM')
            check = db.execute('PRAGMA integrity_check').fetchone()[0]
            if check != 'ok':
                raise RuntimeError(f'Database integrity check failed: {check}')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('instance/food_reviews.sqlite3'))
    parser.add_argument('--target', type=Path, default=Path('instance/public_seed.sqlite3'))
    arguments = parser.parse_args()
    prepare(arguments.source, arguments.target)
    with closing(sqlite3.connect(arguments.target)) as db:
        restaurants = db.execute('SELECT count(*) FROM restaurants').fetchone()[0]
        reviews = db.execute('SELECT count(*) FROM reviews').fetchone()[0]
        accounts = db.execute('SELECT count(*) FROM accounts').fetchone()[0]
    print(f'{arguments.target}: {restaurants} restaurants, {reviews} reviews, {accounts} accounts')
