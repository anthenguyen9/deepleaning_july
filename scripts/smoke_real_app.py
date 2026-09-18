"""Exercise real stored reviews on a private database copy, with external APIs disabled."""
import argparse
import json
import os
import secrets
import sqlite3
from pathlib import Path

from gemini_service import GeminiError
from pipeline import dump
from webapp import create_app


class OfflineProvider:
    def extract_query(self,*args,**kwargs): raise GeminiError('Deliberate provider outage for offline smoke')
    def advise(self,*args,**kwargs): raise GeminiError('Deliberate provider outage for offline smoke')


def run(source,target,report,live_provider=False):
    if target.exists():raise ValueError('Smoke copy exists; use a new path')
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as db,sqlite3.connect(target) as copy:db.backup(copy)
    os.environ['ASSISTANT_REFRESH_ON_QUERY']='0'
    os.environ['DEPLOYMENT_MODE']='local'
    os.environ['ASSISTANT_OPENAI_FALLBACK']='0'
    password=secrets.token_urlsafe(24)
    app=create_app({'TESTING':True,'DATABASE':str(target),'ADMIN_USERNAME':'__research_smoke__',
                    'ADMIN_PASSWORD':password,'RETRIEVAL_METHOD':'bm25'},gemini_factory=None if live_provider else OfflineProvider)
    client=app.test_client();client.get('/login')
    with client.session_transaction() as s:token=s['csrf']
    r=client.post('/login',data={'csrf':token,'username':'__research_smoke__','password':password},follow_redirects=True)
    assert r.status_code==200
    with client.session_transaction() as s:token=s['csrf'];user=s['user_id']
    pages={p:client.get(p).status_code for p in ['/','/assistant','/research','/profile','/admin/','/admin/locations/']}
    assert all(v==200 for v in pages.values()),pages
    cases=[]
    queries=['Quán hải sản ở Hòa Xuân Đà Nẵng','Quán thịt nướng gần Hải Châu',
             'Quán hải sản có view biển ở Đà Nẵng','Seafood restaurant in Son Tra Da Nang']
    for query in queries[:1] if live_provider else queries:
        response=client.post('/assistant',data={'csrf':token,'message':query},follow_redirects=True)
        assert response.status_code==200
        with sqlite3.connect(target) as db:
            row=db.execute("SELECT content,context_json FROM assistant_messages WHERE user_id=? AND role='assistant' ORDER BY id DESC LIMIT 1",(user,)).fetchone()
        ctx=json.loads(row[1]);assert not ctx.get('error'),ctx
        cases.append({'query':query,'http':response.status_code,'location':ctx.get('location'),
                      'candidates':len(ctx.get('candidate_ids',[])),'citation_status':ctx.get('citation_status'),
                      'source_count':len(ctx.get('citations',[])),'query_fallback':ctx.get('query_fallback')})
    result={'database_copy':str(target),'external_api_mode':'live Gemini, crawl and OpenAI disabled' if live_provider else 'disabled',
            'pages':pages,'assistant_cases':cases,
            'interpretation':'Operational integration; not a relevance, faithfulness or user study score.'}
    dump(report,result);print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=Path('instance/food_reviews.sqlite3'))
    p.add_argument('--target',type=Path,required=True)
    p.add_argument('--report',type=Path,default=Path('outputs/real_app_smoke.json'))
    p.add_argument('--live-provider',action='store_true',help='Allow real Gemini calls for one query; OpenAI and crawl remain disabled')
    a=p.parse_args();run(a.source,a.target,a.report,a.live_provider)
