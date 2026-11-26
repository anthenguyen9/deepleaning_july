"""Measure retrieval operations and prepare a blinded pool; never infer relevance labels."""
import argparse
import random
import time
from pathlib import Path

import numpy as np
import torch

from pipeline import dump, read
from retrieval_service import retrieve
from storage import Store


def run(db, pack, output):
    torch.set_num_threads(2)
    store = Store(db)
    queries = read(pack / 'retrieval_queries.json')
    pool_path = pack / 'retrieval_blinded_pool.json'
    if pool_path.exists():
        raise ValueError('Preserve existing reviewer work; choose a new pack directory')
    methods = ('bm25', 'dense', 'hybrid')
    timings = {m: [] for m in methods}
    counts = {m: [] for m in methods}
    mapping, forms = [], []
    rng = random.Random(42)
    for query in queries:
        documents = {}
        for method in methods:
            started = time.perf_counter()
            result = retrieve(store, query['query'], limit=5, method=method, fallback=False, log=False)
            timings[method].append((time.perf_counter() - started) * 1000)
            counts[method].append(len(result['results']))
            mapping.append({'query_id': query['id'], 'method': method,
                            'keys': [r['document_key'] for r in result['results']]})
            for row in result['results']:
                documents[row['document_key']] = {
                    'document_key': row['document_key'], 'text': row['text'],
                    'restaurant_name': row['restaurant_name'], 'restaurant_id': row['restaurant_id'],
                    'relevance': None, 'reviewed': False}
        candidates = list(documents.values())
        rng.shuffle(candidates)
        forms.append({'id': query['id'], 'query': query['query'], 'split': query['split'],
                      'candidates': candidates})
    dump(pool_path, forms)
    dump(pack / 'retrieval_private_mapping.json', mapping)
    report = {'queries': len(queries), 'top_k': 5, 'fallback': False,
              'relevance_status': 'unjudged; no Recall, MRR or nDCG claimed',
              'timing_protocol': 'One sequential pass; first dense query includes model startup; no concurrent training',
              'methods': {m: {'returned': sum(counts[m]), 'empty_queries': counts[m].count(0),
                              'first_query_ms': timings[m][0],
                              'remaining_median_ms': float(np.median(timings[m][1:])),
                              'remaining_p95_ms': float(np.percentile(timings[m][1:], 95))} for m in methods},
              'pooled_documents': sum(len(f['candidates']) for f in forms)}
    dump(output, report)
    print(report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='instance/food_reviews.sqlite3')
    parser.add_argument('--pack', type=Path, default=Path('data/evaluation_20260919'))
    parser.add_argument('--output', type=Path, default=Path('outputs/retrieval_operational.json'))
    args = parser.parse_args()
    run(args.db, args.pack, args.output)
