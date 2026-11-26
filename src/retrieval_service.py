"""SQLite FTS5 retrieval and reproducible IR metrics for FoodLens."""
import json
import math
import re
import time
from pathlib import Path

from storage import utcnow


def fts_query(text):
    tokens=re.findall(r"[^\W_]+",str(text or '').lower(),flags=re.UNICODE)
    tokens=[t for t in tokens if len(t)>=2][:16]
    return ' OR '.join('"'+t.replace('"','""')+'"' for t in dict.fromkeys(tokens))


def _bm25(store,query,restaurant_ids=None,limit=8,search_id=None,log=True):
    if not 1<=limit<=50: raise ValueError('limit phải từ 1 đến 50.')
    match=fts_query(query)
    if not match: return {'method':'bm25','results':[],'duration_ms':0.0,'query':match}
    if restaurant_ids is not None and not restaurant_ids:
        return {'method':'bm25','results':[],'duration_ms':0.0,'query':match}
    restaurant_ids=list(dict.fromkeys(restaurant_ids or []))
    started=time.perf_counter()
    sql='''SELECT d.*,bm25(review_fts) raw_score FROM review_fts
        JOIN review_documents d USING(document_key) WHERE review_fts MATCH ?'''
    params=[match]
    if restaurant_ids:
        sql+=' AND d.restaurant_id IN ('+','.join('?' for _ in restaurant_ids)+')'
        params.extend(restaurant_ids)
    sql+=' ORDER BY raw_score,d.document_key LIMIT ?';params.append(limit)
    with store.connect() as db:
        rows=db.execute(sql,params).fetchall()
    elapsed=round((time.perf_counter()-started)*1000,3)
    results=[]
    for rank,row in enumerate(rows,1):
        item=dict(row);metadata=json.loads(item.pop('metadata_json'))
        raw=item.pop('raw_score');item.update(metadata=metadata,score=round(-raw,6),rank=rank)
        results.append(item)
    if log:
        with store.connect() as db:
            db.execute('''INSERT INTO retrieval_events(search_id,query,method,candidate_restaurants,
                result_count,result_keys_json,duration_ms,created_at) VALUES(?,?,?,?,?,?,?,?)''',
                (search_id,query,'bm25',len(restaurant_ids),len(results),
                 json.dumps([r['document_key'] for r in results],ensure_ascii=False),elapsed,utcnow()))
    return {'method':'bm25','results':results,'duration_ms':elapsed,'query':match}


def retrieve(store,query,restaurant_ids=None,limit=8,search_id=None,log=True,
             method='bm25',fallback=False):
    if method not in {'bm25','dense','hybrid'} or not 1<=limit<=50:
        raise ValueError('Invalid retrieval method or limit')
    if method=='bm25': return _bm25(store,query,restaurant_ids,limit,search_id,log)
    from dense_service import dense_retrieve,DenseUnavailable
    started=time.perf_counter()
    try:
        dense=dense_retrieve(store,query,restaurant_ids,50) if query.strip() else []
    except (DenseUnavailable,ImportError,OSError):
        if not fallback: raise
        result=_bm25(store,query,restaurant_ids,limit,search_id,log)
        result.update(requested_method=method,fallback_reason='dense_index_unavailable')
        return result
    if method=='dense': results=dense[:limit]
    else:
        lexical=_bm25(store,query,restaurant_ids,50,log=False)['results']
        combined={};scores={}
        for ranking in (lexical,dense):
            for rank,item in enumerate(ranking,1):
                key=item['document_key'];combined[key]=item
                scores[key]=scores.get(key,0)+1/(60+rank)
        keys=sorted(scores,key=lambda key:(-scores[key],key))[:limit]
        results=[dict(combined[key],score=scores[key],rank=i) for i,key in enumerate(keys,1)]
    duration=round((time.perf_counter()-started)*1000,3)
    if log:
        with store.connect() as db:
            db.execute('''INSERT INTO retrieval_events(search_id,query,method,candidate_restaurants,
                result_count,result_keys_json,duration_ms,created_at) VALUES(?,?,?,?,?,?,?,?)''',
                (search_id,query,method,len(restaurant_ids or []),len(results),
                 json.dumps([r['document_key'] for r in results]),duration,utcnow()))
    return {'method':method,'results':results,'duration_ms':duration,'query':query}


def _metrics(ranked,relevant,k):
    relevant=set(relevant);top=ranked[:k]
    if not relevant: return None
    hits=[1 if item in relevant else 0 for item in top]
    recall=sum(hits)/len(relevant)
    reciprocal=next((1/i for i,item in enumerate(ranked,1) if item in relevant),0.0)
    dcg=sum(rel/math.log2(i+2) for i,rel in enumerate(hits))
    idcg=sum(1/math.log2(i+2) for i in range(min(len(relevant),k)))
    return {'recall_at_k':round(recall,6),'mrr':round(reciprocal,6),
            'ndcg_at_k':round(dcg/idcg if idcg else 0,6)}


def evaluate(store,query_file,k=5,output_path=None,method='bm25',split=None):
    rows=json.loads(Path(query_file).read_text(encoding='utf-8'))
    if not 1<=k<=50: raise ValueError('k must be 1..50')
    details=[]
    for row in rows:
        if split and row.get('split')!=split: continue
        relevant_reviews=row.get('relevant_review_ids',[])
        relevant_restaurants=row.get('relevant_restaurant_ids',[])
        if not relevant_reviews and not relevant_restaurants: continue
        result=retrieve(store,row['query'],row.get('candidate_restaurant_ids'),limit=50,log=False,method=method)
        review_rank=[r['metadata']['review_id'] for r in result['results']]
        restaurant_rank=[]
        for item in result['results']:
            rid=item['restaurant_id']
            if rid not in restaurant_rank: restaurant_rank.append(rid)
        details.append({'id':row['id'],'split':row.get('split'),'query':row['query'],
            'review_metrics':_metrics(review_rank,relevant_reviews,k),
            'restaurant_metrics':_metrics(restaurant_rank,relevant_restaurants,k),
            'latency_ms':result['duration_ms'],'retrieved_review_ids':review_rank[:k],
            'retrieved_restaurant_ids':restaurant_rank[:k]})
    def aggregate(key):
        values=[d[key] for d in details if d[key] is not None]
        if not values:return None
        return {metric:round(sum(v[metric] for v in values)/len(values),6)
                for metric in ['recall_at_k','mrr','ndcg_at_k']}|{'judged_queries':len(values)}
    report={'method':method,'mrr_depth':50,'split':split,'k':k,'queries_in_file':len(rows),
        'judged_queries':len(details),'review':aggregate('review_metrics'),
        'restaurant':aggregate('restaurant_metrics'),'details':details}
    if output_path:
        path=Path(output_path);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
