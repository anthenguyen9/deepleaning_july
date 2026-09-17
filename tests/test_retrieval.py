import json
import tempfile
import unittest
from pathlib import Path

from retrieval_service import evaluate, fts_query, retrieve
from storage import Store, utcnow


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=Store(self.root/'retrieval.sqlite3')
        with self.store.connect() as db:
            for rid,name in [('r1','Quán Việt'),('r2','Quán Chay')]:
                db.execute('INSERT INTO restaurants VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (rid,name,'Đà Nẵng',4.5,10,'','Vietnamese','',utcnow(),'{}'))
            reviews=[('r1','v1','Món ăn ngon và phục vụ tốt.',5),
                     ('r1','v2','Giá hơi cao.',3),('r2','v3','Không gian yên tĩnh.',5)]
            for rid,vid,text,rating in reviews:
                db.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?)',
                    (rid,vid,text,rating,'2026-08-01T00:00:00+00:00','', '',utcnow(),'{}'))
                key=rid+':'+vid;metadata=json.dumps({'restaurant_id':rid,'review_id':vid,
                    'rating':rating,'published_at':'2026-08-01T00:00:00+00:00','labels':[],'source_url':''})
                name='Quán Việt' if rid=='r1' else 'Quán Chay'
                db.execute('INSERT INTO review_documents VALUES(?,?,?,?,?,?,?,?)',
                    (key,rid,vid,text,name,'Vietnamese',metadata,utcnow()))
                db.execute('INSERT INTO review_fts VALUES(?,?,?,?)',(key,text,name,'Vietnamese'))

    def tearDown(self): self.temp.cleanup()

    def test_query_filter_and_logging(self):
        self.assertNotIn("'",fts_query("món ngon' OR *"))
        result=retrieve(self.store,'món ngon',['r1'],limit=5,search_id=None)
        self.assertEqual(result['method'],'bm25')
        self.assertEqual(result['results'][0]['metadata']['review_id'],'v1')
        self.assertTrue(all(x['restaurant_id']=='r1' for x in result['results']))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM retrieval_events').fetchone()[0],1)

    def test_metrics(self):
        queries=[{'id':'q1','query':'món ngon','split':'dev','relevant_restaurant_ids':['r1'],
                  'relevant_review_ids':['v1']},
                 {'id':'unjudged','query':'giá','split':'test','relevant_restaurant_ids':[],
                  'relevant_review_ids':[]}]
        path=self.root/'queries.json';path.write_text(json.dumps(queries,ensure_ascii=False),encoding='utf-8')
        report=evaluate(self.store,path,k=5,output_path=self.root/'metrics.json')
        self.assertEqual(report['judged_queries'],1)
        self.assertEqual(report['review']['recall_at_k'],1.0)
        self.assertEqual(report['restaurant']['mrr'],1.0)
        self.assertTrue((self.root/'metrics.json').exists())


if __name__=='__main__': unittest.main()
