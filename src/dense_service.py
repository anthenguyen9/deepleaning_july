"""Local multilingual embeddings with a text-hash keyed SQLite cache."""
import hashlib
import json
import os
import threading
from functools import lru_cache

import numpy as np

MODEL = 'intfloat/multilingual-e5-small'
_lock = threading.Lock()


class DenseUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=2)
def _encoder(model):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model)


def encode(texts, model, query=False):
    prefix = 'query: ' if query else 'passage: '
    with _lock:
        return _encoder(model).encode([prefix + text for text in texts], batch_size=32,
                                      normalize_embeddings=True, show_progress_bar=False)


def _text(row):
    return ' '.join((row['restaurant_name'] or '', row['category'] or '', row['text']))


def _hash(row):
    return hashlib.sha256(_text(row).encode('utf-8')).hexdigest()


def _schema(store):
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS dense_vectors (
            document_key TEXT NOT NULL,model TEXT NOT NULL,text_hash TEXT NOT NULL,
            vector BLOB NOT NULL,dimension INTEGER NOT NULL,
            PRIMARY KEY(document_key,model))''')


def build_dense(store, model=None, embed=None):
    model = model or os.getenv('EMBEDDING_MODEL', MODEL)
    _schema(store)
    with store.connect() as db:
        rows = [dict(r) for r in db.execute('SELECT * FROM review_documents ORDER BY document_key')]
        cached = {r['document_key']: r['text_hash'] for r in db.execute(
            'SELECT document_key,text_hash FROM dense_vectors WHERE model=?', (model,))}
    pending = [r for r in rows if cached.get(r['document_key']) != _hash(r)]
    for start in range(0, len(pending), 32):
        batch = pending[start:start+32]
        vectors = (embed or encode)([_text(r) for r in batch], model, query=False)
        if len(vectors) != len(batch):
            raise ValueError('Embedding count mismatch')
        with store.connect() as db:
            for row, v in zip(batch, vectors):
                v = np.asarray(v, dtype=np.float32)
                norm = np.linalg.norm(v)
                if v.ndim != 1 or not np.isfinite(v).all() or norm == 0:
                    raise ValueError('Invalid embedding')
                v /= norm
                db.execute('INSERT OR REPLACE INTO dense_vectors VALUES(?,?,?,?,?)',
                    (row['document_key'], model, _hash(row), v.tobytes(), len(v)))
    with store.connect() as db:
        db.execute('DELETE FROM dense_vectors WHERE document_key NOT IN (SELECT document_key FROM review_documents)')
    return {'model': model, 'indexed': len(rows), 'encoded': len(pending)}


def dense_retrieve(store, query, restaurant_ids=None, limit=8, model=None, embed=None):
    model = model or os.getenv('EMBEDDING_MODEL', MODEL)
    _schema(store)
    if restaurant_ids is not None and not restaurant_ids:
        return []
    sql = '''SELECT d.*,v.vector,v.dimension,v.text_hash FROM review_documents d
             LEFT JOIN dense_vectors v ON v.document_key=d.document_key AND v.model=?'''
    params = [model]
    if restaurant_ids is not None:
        sql += ' WHERE d.restaurant_id IN (' + ','.join('?' for _ in restaurant_ids) + ')'
        params.extend(restaurant_ids)
    with store.connect() as db:
        rows = [dict(r) for r in db.execute(sql, params)]
    if not rows:
        return []
    if any(r['vector'] is None or r['text_hash'] != _hash(r) for r in rows):
        raise DenseUnavailable('Dense index missing or stale; run research.py build-dense')
    v = np.asarray((embed or encode)([query], model, query=True)[0], dtype=np.float32)
    norm = np.linalg.norm(v)
    if not np.isfinite(v).all() or norm == 0:
        raise DenseUnavailable('Invalid query embedding')
    v /= norm
    results = []
    for row in rows:
        if row.pop('dimension') != len(v):
            raise DenseUnavailable('Embedding dimensions differ')
        row['score'] = float(np.frombuffer(row.pop('vector'), dtype=np.float32) @ v)
        row.pop('text_hash')
        row['metadata'] = json.loads(row.pop('metadata_json'))
        results.append(row)
    results.sort(key=lambda r: (-r['score'], r['document_key']))
    return [dict(row, rank=i) for i, row in enumerate(results[:limit], 1)]
