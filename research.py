"""Offline research commands; functional examples are never reported as study data."""
import argparse
import csv
import hashlib
import json
import random
import statistics
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from data_pipeline import DEFAULT_DB,ROOT,build_index,status
from pipeline import CLASSES,dump,normalize
from storage import Store


def annotation_template(store,output,limit=1000,seed=42):
    with store.connect() as db:
        rows=[dict(r) for r in db.execute("SELECT restaurant_id,id,text,published_at,rating FROM reviews WHERE trim(text)<>'' ORDER BY restaurant_id,id")]
    unique={}
    for row in rows: unique.setdefault(normalize(row['text']).casefold(),row)
    rows=list(unique.values());random.Random(seed).shuffle(rows)
    target=Path(output)
    if target.exists(): raise ValueError('Annotation file exists; refusing to overwrite human work')
    records=[{'restaurant_id':r['restaurant_id'],'review_id':r['id'],'text':r['text'],
              'published_at':r['published_at'],'rating':r['rating'],'labels':[],
              'annotator':'','reviewed':False} for r in rows[:limit]]
    dump(target,{'source':'SerpApi','seed':seed,'records':records})
    return {'exported':len(records),'status':'awaiting_human_labels','path':str(target)}


def prepare_gold(source,output,seed=42):
    raw=json.loads(Path(source).read_text(encoding='utf-8-sig'))['records']
    rows=[];texts={};ids=set()
    for r in raw:
        if r.get('reviewed') is not True or not r.get('annotator'):
            raise ValueError('All records need a human annotator and reviewed=true')
        labels=r.get('labels')
        if not isinstance(labels,list) or any(x not in CLASSES for x in labels):
            raise ValueError('Invalid ABSA labels')
        text=normalize(r['text']);key=text.casefold();labels=sorted(set(labels))
        if not text: raise ValueError('Empty review')
        if key in texts:
            if texts[key]!=labels: raise ValueError('Conflicting exact duplicates need adjudication')
            continue
        texts[key]=labels;uid=r['restaurant_id']+':'+r['review_id']
        if uid in ids: raise ValueError('Duplicate review identity')
        ids.add(uid);rows.append({'id':uid,'restaurant_id':r['restaurant_id'],'text':text,'labels':labels})
    groups=sorted({r['restaurant_id'] for r in rows});random.Random(seed).shuffle(groups)
    if len(groups)<3: raise ValueError('Need three restaurant groups for disjoint train/dev/test')
    a=min(len(groups)-2,max(1,int(len(groups)*.7)))
    b=min(len(groups)-1,max(a+1,int(len(groups)*.8)))
    splits={'train':set(groups[:a]),'dev':set(groups[a:b]),'test':set(groups[b:])}
    destination=Path(output)
    if any((destination/f'{s}.json').exists() for s in splits):
        raise ValueError('Locked split exists; refusing to overwrite')
    for split,restaurants in splits.items():
        dump(destination/f'{split}.json',[r for r in rows if r['restaurant_id'] in restaurants])
    report={'seed':seed,'source_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            'policy':'restaurant-disjoint, exact-text deduplicated',
            'counts':{s:sum(r['restaurant_id'] in v for r in rows) for s,v in splits.items()}}
    dump(destination/'manifest.json',report);return report


def agreement(first,second):
    from sklearn.metrics import cohen_kappa_score
    import numpy as np
    def records(path):
        data=json.loads(Path(path).read_text(encoding='utf-8-sig'))['records']
        return {(x['restaurant_id'],x['review_id']):x for x in data if x.get('reviewed') and x.get('annotator')}
    a,b=records(first),records(second);shared=sorted(a.keys()&b.keys())
    if not shared: raise ValueError('No independently reviewed shared records')
    kappa={}
    for label in CLASSES:
        x=[int(label in a[k]['labels']) for k in shared]
        y=[int(label in b[k]['labels']) for k in shared]
        score=cohen_kappa_score(x,y) if len(set(x+y))>1 else float('nan')
        kappa[label]=float(score) if np.isfinite(score) else None
    return {'paired_reviews':len(shared),'exact_agreement':sum(set(a[k]['labels'])==set(b[k]['labels']) for k in shared)/len(shared),
            'kappa_per_label':kappa}


def retrieval_comparison(store,queries,output,k=5,split=None):
    from retrieval_service import evaluate
    import numpy as np
    reports={}
    for method in ('bm25','dense','hybrid'):
        report=evaluate(store,queries,k,method=method,split=split)
        times=[d['latency_ms'] for d in report['details']]
        report['latency_ms']={'p50':float(np.percentile(times,50)) if times else None,
                              'p95':float(np.percentile(times,95)) if times else None}
        reports[method]=report
    result={'query_sha256':hashlib.sha256(Path(queries).read_bytes()).hexdigest(),
            'reports':reports,'warning':'Only independent judgments support research conclusions.'}
    dump(Path(output),result);return result


def study_summary(source):
    with Path(source).open(encoding='utf-8-sig',newline='') as file: rows=list(csv.DictReader(file))
    fields=('usefulness','ease_of_use','trust','relevance','reuse_intent')
    result={}
    for condition in ('baseline','personalized'):
        selected=[r for r in rows if r.get('condition')==condition and r.get('consent')=='yes']
        item={'participants':len({r['participant_id'] for r in selected}),'responses':len(selected)}
        for field in fields:
            values=[float(r[field]) for r in selected if r.get(field)]
            if any(not 1<=x<=5 for x in values): raise ValueError('Likert scores must be 1..5')
            item[field]={'mean':statistics.mean(values) if values else None,
                         'median':statistics.median(values) if values else None}
        result[condition]=item
    result['status']='observed_data' if rows else 'awaiting_participants'
    return result


def serp_quota():
    key=os.getenv('SERPAPI_API_KEY','').strip()
    if not key: raise ValueError('SERPAPI_API_KEY is not configured')
    url='https://serpapi.com/account.json?'+urllib.parse.urlencode({'api_key':key})
    try:
        with urllib.request.urlopen(url,timeout=20) as response:
            account=json.load(response)
    except (urllib.error.URLError,TimeoutError,ValueError):
        raise ValueError('Could not read SerpApi account status') from None
    return {field:account.get(field) for field in ('plan_name','searches_per_month',
        'this_month_usage','total_searches_left','account_rate_limit_per_hour')}


def main():
    load_dotenv(ROOT/'.env')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',default=str(DEFAULT_DB))
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('status');sub.add_parser('build-dense');sub.add_parser('serp-quota')
    a=sub.add_parser('annotation-template');a.add_argument('--output',default='data/annotation.json');a.add_argument('--limit',type=int,default=1000)
    a=sub.add_parser('prepare-gold');a.add_argument('--input',required=True);a.add_argument('--output',default='data/gold')
    a=sub.add_parser('agreement');a.add_argument('first');a.add_argument('second')
    a=sub.add_parser('evaluate-retrieval');a.add_argument('--queries',required=True);a.add_argument('--output',default='outputs/retrieval_comparison.json');a.add_argument('--k',type=int,default=5);a.add_argument('--split',choices=['dev','test'])
    a=sub.add_parser('study-summary');a.add_argument('--input',required=True);a.add_argument('--output',default='outputs/study_summary.json')
    args=p.parse_args();store=Store(args.db)
    if args.command=='status': result=status(store)
    elif args.command=='serp-quota': result=serp_quota()
    elif args.command=='build-dense':
        from dense_service import build_dense
        build_index(store);result=build_dense(store)
    elif args.command=='annotation-template': result=annotation_template(store,args.output,args.limit)
    elif args.command=='prepare-gold': result=prepare_gold(args.input,args.output)
    elif args.command=='agreement': result=agreement(args.first,args.second)
    elif args.command=='evaluate-retrieval': result=retrieval_comparison(store,args.queries,args.output,args.k,args.split)
    else: result=study_summary(args.input);dump(Path(args.output),result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
