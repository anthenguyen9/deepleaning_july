import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from data_pipeline import build_index
from dense_service import DenseUnavailable,build_dense,dense_retrieve
from gemini_service import GeminiClient,GeminiError
from restaurant_service import save_restaurant,save_reviews
from retrieval_service import retrieve
from storage import Store,utcnow


def fake_embed(texts,model,query=False):
    return np.asarray([[0.,1.] if 'giá' in text.lower() else [1.,0.] for text in texts],dtype=np.float32)


class HybridResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.sqlite3')
        for rid,title,review in [('a','Quán ngon','Món ngon.'),('b','Quán giá','Giá rẻ.')]:
            save_restaurant(self.store,{'data_id':rid,'title':title},utcnow())
            save_reviews(self.store,rid,[{'review_id':'v1','snippet':review,
                           'iso_date':'2026-01-01T00:00:00Z'}],utcnow())
        build_index(self.store)
    def tearDown(self): self.tmp.cleanup()

    def test_hybrid_respects_filter_and_stale_vectors(self):
        build_dense(self.store,model='fake',embed=fake_embed)
        self.assertEqual(dense_retrieve(self.store,'giá',['b'],model='fake',embed=fake_embed)[0]['restaurant_id'],'b')
        self.assertEqual(dense_retrieve(self.store,'giá',[],model='fake',embed=fake_embed),[])
        self.assertEqual(retrieve(self.store,'giá',[],method='bm25')['results'],[])
        with patch('dense_service.dense_retrieve',side_effect=lambda *a,**kw:
                   dense_retrieve(*a,model='fake',embed=fake_embed,**kw)):
            result=retrieve(self.store,'giá',['a','b'],method='hybrid')
        self.assertEqual(result['results'][0]['restaurant_id'],'b')
        save_reviews(self.store,'b',[{'review_id':'v1','snippet':'Updated text'}],utcnow())
        build_index(self.store)
        with self.assertRaises(DenseUnavailable):
            dense_retrieve(self.store,'giá',model='fake',embed=fake_embed)

    def test_citation_must_cover_recommended_restaurant(self):
        restaurants=[{'id':'a','name':'A','assessment':{'evidence':[{'id':'v1','text':'Good food.'}]}},
                     {'id':'b','name':'B','assessment':{'evidence':[{'id':'v2','text':'Low price.'}]}}]
        payload={'reply':'Chọn B [R1].','learned_preferences':'',
                 'recommended_restaurant_ids':['b'],'citations':['R1']}
        result=GeminiClient(key='fake',transport=lambda _:payload).advise({}, {}, [], [], restaurants,'recommend')
        self.assertTrue(result['abstained'])
        self.assertNotIn('Chọn B',result['reply'])
        with self.assertRaises(GeminiError):
            GeminiClient(key='fake',transport=lambda _:{'output_text':'[]'}).advise({}, {}, [], [], restaurants,'recommend')


if __name__=='__main__': unittest.main()
