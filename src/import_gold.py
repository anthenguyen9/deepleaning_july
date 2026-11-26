"""Import independently reviewed gold labels into the existing application DB."""
import argparse
import json
from pathlib import Path

from admin_annotations import text_hash
from data_pipeline import DEFAULT_DB
from pipeline import CLASSES
from storage import Store, utcnow


def import_gold(source, database=DEFAULT_DB):
    path=Path(database).resolve()
    if not path.is_file():
        raise FileNotFoundError(f'Database does not exist: {path}. Start webapp once to initialize it.')
    records=json.loads(Path(source).read_text(encoding='utf-8-sig'))['records']
    store=Store(path)  # Additive schema initialization; never creates an accidental cwd database.
    count=0
    with store.connect() as db:
        required={'reviews','restaurants','gold_annotations'}
        found={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= found: raise RuntimeError(f'Missing tables: {sorted(required-found)}')
        for record in records:
            if record.get('annotation_origin')=='ai' or str(record.get('annotator','')).lower().startswith('ai:'):
                continue
            labels=record.get('labels')
            if record.get('reviewed') is not True or not record.get('annotator') or not isinstance(labels,list):
                continue
            if any(label not in CLASSES for label in labels): raise ValueError('Invalid ABSA label')
            row=db.execute('SELECT text FROM reviews WHERE restaurant_id=? AND id=?',
                           (record['restaurant_id'],record['review_id'])).fetchone()
            if row is None: continue
            digest=text_hash(row['text'])
            if record.get('text') != row['text']:
                raise ValueError('Review text changed; refuse stale gold label')
            db.execute('''INSERT INTO gold_annotations VALUES(?,?,?,?,?,?)
                ON CONFLICT(restaurant_id,review_id) DO UPDATE SET
                text_hash=excluded.text_hash,labels_json=excluded.labels_json,
                annotator=excluded.annotator,reviewed_at=excluded.reviewed_at''',
                (record['restaurant_id'],record['review_id'],digest,
                 json.dumps(sorted(set(labels))),record['annotator'],utcnow()))
            count+=1
    return count


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',help='Export from /admin/export or another human-reviewed JSON')
    parser.add_argument('--db',default=str(DEFAULT_DB))
    args=parser.parse_args()
    print(f'Imported {import_gold(args.source,args.db)} annotations')
