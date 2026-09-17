import tempfile
import unittest
from pathlib import Path

from data_pipeline import (add_seed, analyze_pending, build_index, compute_trends,
                           ingest_restaurants, ingest_reviews, search_index, snapshot, status)
from restaurant_service import SerpClient
from storage import Store


def api(params):
    if params['engine'] == 'google_maps':
        return {'local_results': [
            {'data_id': 'r1', 'title': 'Quán Việt', 'rating': 4.6, 'reviews': 120,
             'address': 'Hải Châu', 'type': 'Vietnamese'},
            {'place_id': 'p2', 'title': 'Quán Chay', 'rating': 4.3, 'reviews': 80,
             'address': 'Sơn Trà', 'type': 'Vegetarian'}]}
    if params.get('next_page_token') == 'page-2':
        return {'reviews': [{'review_id': 'v2', 'snippet': 'Phục vụ chậm.', 'rating': 2,
                             'iso_date': '2026-08-02T00:00:00Z'}]}
    rid = params.get('data_id') or params.get('place_id')
    response = {'reviews': [{'review_id': rid + '-v1', 'snippet': 'Món rất ngon.', 'rating': 5,
                             'iso_date': '2026-08-01T00:00:00Z'}]}
    if rid == 'r1':
        response['serpapi_pagination'] = {'next_page_token': 'page-2'}
    return response


class FakeVectorizer:
    def transform(self, texts):
        return texts


class FakeModel:
    def predict(self, texts):
        return [[1, 0] for _ in texts]


class FakeAnalyzer:
    version = 'fake-v1'
    bundle = {'vectorizer': FakeVectorizer(), 'model': FakeModel(),
              'classes': ['food:POSITIVE', 'service:NEGATIVE']}


class IncrementalPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'pipeline.sqlite3')
        self.client = SerpClient(self.store, key='fake-key', transport=api, daily_limit=50)

    def tearDown(self):
        self.temp.cleanup()

    def test_incremental_end_to_end(self):
        self.assertEqual(add_seed(self.store, 'Hải Châu', 'món Việt')['area'], 'Hải Châu')
        first = ingest_restaurants(self.store, self.client, 'Đà Nẵng', '', 20)
        self.assertEqual(first['inserted'], 2)
        second = ingest_restaurants(self.store, self.client, 'Đà Nẵng', '', 20)
        self.assertEqual(second['updated'], 2)

        crawled = ingest_reviews(self.store, self.client, max_restaurants=2, pages=2)
        self.assertEqual(crawled['restaurants_attempted'], 2)
        self.assertEqual(crawled['restaurants_complete'], 2)
        self.assertEqual(crawled['reviews_received'], 3)
        self.assertEqual(status(self.store)['reviews'], 3)

        analyzed = analyze_pending(self.store, FakeAnalyzer(), limit=10)
        self.assertEqual(analyzed['analyzed'], 3)
        self.assertEqual(analyze_pending(self.store, FakeAnalyzer(), limit=10)['analyzed'], 0)

        trends = compute_trends(self.store, 'fake-v1')
        self.assertEqual(trends['dated_reviews'], 3)
        self.assertEqual(trends['claim'], 'retrospective-baseline-not-BERTrend')

        index = build_index(self.store, 'fake-v1')
        self.assertEqual(index['indexed'], 3)
        matches = search_index(self.store, 'ngon', 5)
        self.assertGreaterEqual(len(matches), 1)
        self.assertIn('metadata', matches[0])

        version = snapshot(self.store, 'test')
        self.assertEqual(version['restaurants'], 2)
        self.assertEqual(version['reviews'], 3)
        current = status(self.store)
        self.assertEqual(current['pending_absa'], 0)
        self.assertEqual(current['dataset_versions'], 1)

    def test_resume_from_saved_page_token(self):
        ingest_restaurants(self.store, self.client, 'Đà Nẵng', '', 1)
        first = ingest_reviews(self.store, self.client, max_restaurants=1, pages=1)
        self.assertEqual(first['restaurants_complete'], 0)
        with self.store.connect() as db:
            state = db.execute("SELECT * FROM restaurant_crawl_state WHERE restaurant_id='r1'").fetchone()
            self.assertEqual(state['next_page_token'], 'page-2')
            self.assertEqual(state['status'], 'pending')
        second = ingest_reviews(self.store, self.client, max_restaurants=1, pages=1)
        self.assertEqual(second['restaurants_complete'], 1)
        self.assertEqual(status(self.store)['reviews'], 2)


if __name__ == '__main__':
    unittest.main()
