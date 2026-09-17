import json
import tempfile
import unittest
from pathlib import Path
from recommendation_service import evaluate_cases, evaluate_file, rank_restaurants

def candidate(rid,rating,category='Món Việt',pos=0,neg=0,n=10):
    return {'id':rid,'name':rid,'category':category,'address':'Đà Nẵng','rating':rating,
            'total_reviews':100,'assessment':{'n_text':n,'aspects':{'food':{
                'POSITIVE':pos,'NEGATIVE':neg,'NEUTRAL':0}}}}

class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.items=[candidate('popular',4.9,'Pizza',1,3),candidate('taste',4.2,'Món Việt',8,0)]
        self.profile={'cuisine':'Món Việt','aspect':'food'}
        self.memory={'explicit_notes':'thích món Việt','learned_summary':''}

    def test_ablation_changes_ranking_and_explains(self):
        a=rank_restaurants(self.items,self.profile,self.memory,[],config='A')
        e=rank_restaurants(self.items,self.profile,self.memory,[],config='E')
        self.assertEqual(a[0]['id'],'popular');self.assertEqual(e[0]['id'],'taste')
        self.assertIn('score_components',e[0]);self.assertIn('khớp hồ sơ',e[0]['recommendation_reason'])

    def test_feedback_penalty(self):
        feedback=[{'restaurant_id':'popular','signal':'dislike','name':'popular','category':'Pizza','note':''}]
        ranked=rank_restaurants(self.items,self.profile,self.memory,feedback,config='D')
        self.assertEqual(ranked[-1]['id'],'popular')

    def test_evaluator_and_file(self):
        cases=[{'candidates':self.items,'profile':self.profile,'memory':self.memory,
                'feedback':[],'relevant_restaurant_ids':['taste']}]
        report=evaluate_cases(cases,k=1)
        self.assertEqual(report['configurations']['A']['recall_at_k'],0)
        self.assertEqual(report['configurations']['E']['recall_at_k'],1)
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'cases.json'; output=Path(d)/'metrics.json'
            source.write_text(json.dumps(cases),encoding='utf-8')
            evaluate_file(source,output,1);self.assertTrue(output.exists())

if __name__=='__main__': unittest.main()
