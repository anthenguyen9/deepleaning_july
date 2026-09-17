import json
import tempfile
import unittest
from pathlib import Path
from storage import Store
from restaurant_service import Analyzer, ApiError, SerpClient, iso_date, now, sanitize, search_area
from webapp import create_app
from gemini_service import GeminiClient, GeminiError
from data_pipeline import build_index

def fake_api(params):
    if params['engine']=='google_maps':
        return {'local_results':[{'data_id':'r1','place_id':'p1','title':'Quán <script>alert(1)</script>',
            'rating':4.5,'reviews':200,'address':'Đà Nẵng'}]}
    return {'reviews':[{'review_id':'v1','snippet':'Món ăn ngon, giá tốt.', 'rating':5,
            'iso_date':'2026-09-01T12:00:00Z','link':'https://www.google.com/maps/reviews/1'},
            {'review_id':'v2','snippet':'<script>alert(2)</script>','rating':2,'date':'một tuần trước','link':'javascript:alert(3)'}]}

class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)
        self.store=Store(self.path/'test.sqlite3')
        self.analyzer=Analyzer(self.path/'missing.joblib')

    def tearDown(self): self.temp.cleanup()

    def client(self,**kw): return SerpClient(self.store,key='fake-key',transport=fake_api,**kw)

    def login_admin(self,client):
        client.get('/login')
        with client.session_transaction() as state: token=state['csrf']
        client.post('/login',data={'csrf':token,'username':'admin','password':'admin'},follow_redirects=True)
        with client.session_transaction() as state: return state['csrf']

    def test_ingestion_cache_dedup_and_date(self):
        sid=search_area(self.store,self.client(),self.analyzer,'Đà Nẵng',limit=1)
        result=self.store.get_search(sid)['result']
        self.assertEqual(result['calls'],2)
        a=result['restaurants'][0]['assessment']
        self.assertEqual(a['n'],2)
        self.assertEqual(a['sample_rating'],3.5)
        self.assertEqual(a['model'],'rating-only')
        self.assertEqual(len(a['months']),1)
        self.assertFalse(a['has_trend_sample'])
        sid2=search_area(self.store,self.client(),self.analyzer,'Đà Nẵng',limit=1)
        r2=self.store.get_search(sid2)['result']
        self.assertEqual(r2['calls'],0);self.assertEqual(r2['cache_hits'],2)
        self.assertEqual(r2['restaurants'][0]['assessment']['n'],2)
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM reviews WHERE id='v2'").fetchone()
            self.assertIsNone(row['published_at']);self.assertEqual(row['source_url'],'')

    def test_quota_reserves_before_call(self):
        client=self.client(daily_limit=1)
        sid=search_area(self.store,client,self.analyzer,'Đà Nẵng',limit=1)
        r=self.store.get_search(sid)
        self.assertEqual(r['status'],'partial');self.assertEqual(r['result']['calls'],1)
        self.assertEqual(r['result']['restaurants'][0]['assessment']['n'],0)

    def test_error_not_cached_or_exposed(self):
        client=SerpClient(self.store,key='fake-secret',transport=lambda p:{'error':'api_key=fake-secret'})
        with self.assertRaises(ApiError) as e: client.fetch({'engine':'google_maps'})
        self.assertNotIn('fake-secret',str(e.exception))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM api_cache').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT status FROM api_calls').fetchone()[0],'failed')

    def test_sanitization(self):
        value=sanitize({'api_key':'secret','nested':{'url':'https://x.test?api_key=secret&n=1'},'v':'secret'},'secret')
        self.assertNotIn('secret',json.dumps(value));self.assertNotIn('api_key',value)

    def test_dates_do_not_invent_timestamp(self):
        self.assertIsNone(iso_date('2 tháng trước'))
        self.assertIsNone(iso_date('2026-01-01'))
        self.assertIsNotNone(iso_date('2026-01-01T01:02:03Z'))

    def test_pagination_bound_and_duplicates(self):
        called=[]
        def paged(params):
            called.append(dict(params))
            response=fake_api(params)
            if params['engine']=='google_maps_reviews': response['serpapi_pagination']={'next_page_token':'same-token'}
            return response
        client=SerpClient(self.store,key='fake',transport=paged)
        sid=search_area(self.store,client,self.analyzer,'Đà Nẵng',limit=1,pages=3)
        self.assertEqual(len(called),3)
        self.assertNotIn('num',called[1]);self.assertEqual(called[2]['num'],20)
        self.assertEqual(self.store.get_search(sid)['result']['restaurants'][0]['assessment']['n'],2)

    def test_profile_csrf_escape_and_history(self):
        app=create_app({'TESTING':True,'DATABASE':str(self.store.path),'MODEL_PATH':str(self.path/'missing')},
            client_factory=lambda s:SerpClient(s,key='fake',transport=fake_api))
        client=app.test_client()
        self.assertEqual(client.get('/').status_code,302)
        token=self.login_admin(client)
        self.assertEqual(client.get('/').status_code,200)
        self.assertEqual(client.post('/search',data={'area':'Đà Nẵng'}).status_code,400)
        result=client.post('/profile',data={'csrf':token,'name':"An'; DROP TABLE profile;--",'area':'Hải Châu',
            'cuisine':'món Việt','aspect':'price','min_rating':'3.5','explicit_notes':'Thích món Việt'},follow_redirects=True)
        self.assertEqual(result.status_code,200)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT aspect FROM accounts WHERE username='admin'").fetchone()[0],'price')
        result=client.post('/search',data={'csrf':token,'area':'Đà Nẵng','limit':'1','pages':'1'},follow_redirects=True)
        self.assertEqual(result.status_code,200)
        self.assertNotIn(b'<script>alert',result.data)
        self.assertIn(b'&lt;script&gt;',result.data)
        self.assertEqual(len(self.store.history()),1)
        self.assertEqual(client.get('/results/999').status_code,404)
        self.assertEqual(client.get('/',headers={'Host':'evil.example'}).status_code,400)
        self.assertIn('Content-Security-Policy',result.headers)

    def test_invalid_input_does_not_call_api(self):
        def forbidden(s): raise AssertionError('API should not run')
        app=create_app({'TESTING':True,'DATABASE':str(self.store.path),'MODEL_PATH':str(self.path/'missing')},client_factory=forbidden)
        client=app.test_client();token=self.login_admin(client)
        response=client.post('/search',data={'csrf':token,'area':'Đà Nẵng','limit':'999'},follow_redirects=True)
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(self.store.history()),0)

    def test_gemini_grounding_and_structured_output(self):
        captured={}
        def transport(body):
            captured.update(body)
            return {'output_text':json.dumps({'reply':'Quán phù hợp là quán trong danh sách [R1].',
                'learned_preferences':'Thích món Việt và nơi yên tĩnh.',
                'recommended_restaurant_ids':['r1','made-up','r1'],'citations':['R1','R999']})}
        client=GeminiClient(key='fake-gemini-key-1234567890',model='gemini-2.5-flash',transport=transport)
        restaurant={'id':'r1','name':'Quán Việt','category':'Vietnamese','assessment':{'n':1,
            'evidence':[{'id':'v1','text':'Món ngon.','rating':5,'source_url':'https://example.test/review'}],'aspects':{}}}
        result=client.advise(self.store.profile(),self.store.memory(),[],[],[restaurant],'Gợi ý giúp tôi')
        self.assertFalse(captured['store'])
        self.assertEqual(captured['model'],'gemini-2.5-flash')
        self.assertEqual(captured['response_format']['mime_type'],'application/json')
        self.assertEqual(result['recommended_restaurant_ids'],['r1'])
        self.assertEqual(result['citations'],['R1'])
        self.assertEqual(result['citation_status'],'valid')
        self.assertNotIn('made-up',result['candidate_ids'])

    def test_gemini_abstains_without_text_evidence(self):
        called=[]
        client=GeminiClient(key='fake-gemini-key-1234567890',transport=lambda body:called.append(body))
        restaurant={'id':'r1','name':'Quán Việt','assessment':{'n':0,'evidence':[],'aspects':{}}}
        result=client.advise(self.store.profile(),self.store.memory(),[],[],[restaurant],'Gợi ý')
        self.assertTrue(result['abstained'])
        self.assertEqual(result['abstention_reason'],'no_text_evidence')
        self.assertEqual(result['recommended_restaurant_ids'],[])
        self.assertEqual(called,[])

    def test_gemini_uses_inline_citations_when_json_list_is_incomplete(self):
        payload={'reply':'Quán này có bình luận về món ăn [R1].','learned_preferences':'',
                 'recommended_restaurant_ids':['r1'],'citations':[]}
        calls=[]
        client=GeminiClient(key='fake',transport=lambda body:(calls.append(body),payload)[1])
        restaurant={'id':'r1','name':'Quán Việt','assessment':{'evidence':[
            {'id':'v1','text':'Món ăn ngon.','source_url':'https://example.test/review'}]}}
        result=client.advise({}, {}, [], [], [restaurant],'Gợi ý')
        self.assertEqual(result['citations'],['R1'])
        self.assertEqual(result['citation_attempts'],1)
        self.assertEqual(len(calls),1)

    def test_gemini_retries_stale_citation_then_uses_local_evidence(self):
        calls=[]
        payload={'reply':'Quán này ngon [R9].','learned_preferences':'',
                 'recommended_restaurant_ids':['r1'],'citations':['R9']}
        def transport(body):
            calls.append(body)
            return payload
        client=GeminiClient(key='fake',transport=transport)
        restaurant={'id':'r1','name':'Quán Việt','address':'Đà Nẵng','assessment':{'evidence':[
            {'id':'v1','text':'Món ăn ngon.','source_url':'https://example.test/review'}]}}
        result=client.advise({}, {}, [], [{'role':'assistant','content':'Quán cũ [R9].'}],
                             [restaurant],'Gợi ý')
        self.assertEqual(len(calls),2)
        self.assertNotIn('[R9]',calls[0]['input'])
        self.assertEqual(result['citation_status'],'fallback')
        self.assertEqual(result['citations'],['R1'])
        self.assertIn('Món ăn ngon',result['reply'])
        self.assertNotIn('Quán này ngon',result['reply'])

    def test_gemini_rejects_uncited_recommendation(self):
        payload={'reply':'Chọn quán này.','learned_preferences':'','recommended_restaurant_ids':['r1'],'citations':[]}
        client=GeminiClient(key='fake-gemini-key-1234567890',transport=lambda body:payload)
        restaurant={'id':'r1','name':'Quán Việt','assessment':{'n':1,
            'evidence':[{'id':'v1','text':'Món ngon.','rating':5}],'aspects':{}}}
        result=client.advise(self.store.profile(),self.store.memory(),[],[],[restaurant],'Gợi ý')
        self.assertEqual(result['recommended_restaurant_ids'],[])
        self.assertEqual(result['citation_status'],'abstained')
        self.assertTrue(result['abstained'])

    def test_gemini_missing_key(self):
        with self.assertRaises(GeminiError):
            GeminiClient(key='',transport=lambda body:{}).advise(self.store.profile(),self.store.memory(),[],[],[],'hello')

    def test_gemini_accepts_direct_structured_rest_response(self):
        payload={'reply':'Có căn cứ.','learned_preferences':'Thích quán yên tĩnh.',
                 'recommended_restaurant_ids':[]}
        client=GeminiClient(key='fake-gemini-key-1234567890',transport=lambda body:payload)
        restaurant={'id':'r1','name':'Quán Việt','assessment':{'n':1,
            'evidence':[{'id':'v1','text':'Món ngon.','rating':5}],'aspects':{}}}
        result=client.advise(self.store.profile(),self.store.memory(),[],[],[restaurant],'hello')
        self.assertTrue(result['abstained'])

    def test_chat_feedback_and_memory_routes(self):
        class FakeGemini:
            def advise(self,*args):
                return {'reply':'R1 phù hợp vì điểm mẫu tốt.','learned_preferences':'Thích món Việt.',
                        'recommended_restaurant_ids':['r1'],'candidate_ids':['r1'],'model':'gemini-test'}
        app=create_app({'TESTING':True,'DATABASE':str(self.store.path),'MODEL_PATH':str(self.path/'missing')},
            client_factory=lambda s:SerpClient(s,key='fake',transport=fake_api),gemini_factory=lambda:FakeGemini())
        client=app.test_client();token=self.login_admin(client)
        response=client.post('/search',data={'csrf':token,'area':'Đà Nẵng','limit':'1','pages':'1'},follow_redirects=False)
        sid=int(response.headers['Location'].rstrip('/').split('/')[-1])
        build_index(self.store,'rating-only')
        response=client.post(f'/results/{sid}/chat',data={'csrf':token,'message':'Tôi thích món Việt'},follow_redirects=True)
        self.assertEqual(response.status_code,200)
        chat=self.store.chat(sid)
        self.assertEqual([m['role'] for m in chat['messages']],['user','assistant'])
        self.assertEqual(chat['messages'][1]['model'],'gemini-test')
        self.assertEqual(chat['messages'][1]['context']['retrieval_method'],'bm25')
        self.assertGreater(chat['messages'][1]['context']['retrieval_result_count'],0)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT learned_summary FROM accounts WHERE username='admin'").fetchone()[0],'Thích món Việt.')
        response=client.post(f'/results/{sid}/feedback/r1',data={'csrf':token,'signal':'like'},follow_redirects=True)
        with self.store.connect() as db:
            self.assertEqual(response.status_code,200)
            self.assertEqual(db.execute('SELECT signal FROM user_feedback').fetchone()[0],'like')
        client.post('/memory/clear',data={'csrf':token})
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT learned_summary FROM accounts WHERE username='admin'").fetchone()[0],'')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user_feedback').fetchone()[0],0)
        client.post(f'/results/{sid}/chat/clear',data={'csrf':token})
        self.assertEqual(self.store.chat(sid)['messages'],[])

if __name__=='__main__': unittest.main()
