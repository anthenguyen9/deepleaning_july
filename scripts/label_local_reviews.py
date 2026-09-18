"""Assign unlabelled review texts with the local SVM and the stated star rule.

These are automatically assigned weak labels, never independently verified gold.
Admin review can replace an automatic assignment later without losing provenance.
"""
import argparse
import hashlib
import json

from pipeline import ASPECTS
from restaurant_service import Analyzer
from storage import Store, utcnow


def label_pending(store, model='outputs/baseline.joblib'):
    analyzer = Analyzer(model)
    if analyzer.bundle is None:
        raise ValueError('The local ABSA model artifact is missing.')
    with store.connect() as db:
        rows = db.execute('''SELECT v.restaurant_id,v.id,v.text,v.rating
            FROM reviews v LEFT JOIN gold_annotations g
              ON g.restaurant_id=v.restaurant_id AND g.review_id=v.id
            WHERE trim(v.text)<>'' AND g.review_id IS NULL
            ORDER BY v.restaurant_id,v.id''').fetchall()
        # Compare hashes in Python so stale predictions are never imported.
        rows = [dict(r) for r in rows]
        predictions = {(r['restaurant_id'], r['review_id']): dict(r) for r in db.execute(
            'SELECT restaurant_id,review_id,text_hash,labels FROM analyses WHERE model_version=?',
            (analyzer.version,))}
    pending = []
    for row in rows:
        digest = hashlib.sha256(row['text'].encode('utf-8')).hexdigest()
        pred = predictions.get((row['restaurant_id'], row['id']))
        if not pred or pred['text_hash'] != digest:
            raise ValueError('A current local model prediction is missing; run analyze-pending first.')
        aspects = {label.partition(':')[0] for label in json.loads(pred['labels'])}
        polarity = ('NEGATIVE' if row['rating'] <= 2 else 'NEUTRAL' if row['rating'] == 3
                    else 'POSITIVE') if row['rating'] in (1, 2, 3, 4, 5) else None
        predicted = json.loads(pred['labels'])
        labels = sorted({f'{aspect}:{polarity}' for aspect in aspects if aspect in ASPECTS}
                        if polarity else set(predicted))
        pending.append((row['restaurant_id'], row['id'], digest,
                        json.dumps(labels, ensure_ascii=False),
                        f'ai:local-{analyzer.version}-star-rule', utcnow()))
    with store.connect() as db:
        db.executemany('''INSERT OR IGNORE INTO gold_annotations
            (restaurant_id,review_id,text_hash,labels_json,annotator,reviewed_at)
            VALUES(?,?,?,?,?,?)''', pending)
    return {'assigned': len(pending), 'source': analyzer.version,
            'policy': 'aspect presence: local SVM; polarity: 1-2 negative, 3 neutral, 4-5 positive',
            'independently_reviewed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='instance/food_reviews.sqlite3')
    args = parser.parse_args()
    print(json.dumps(label_pending(Store(args.db)), ensure_ascii=True))
