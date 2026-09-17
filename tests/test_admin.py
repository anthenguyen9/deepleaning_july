import json
import tempfile
import unittest
from pathlib import Path

from admin_annotations import text_hash
from restaurant_service import save_restaurant, save_reviews
from storage import Store
from webapp import create_app


class AdminAnnotationTests(unittest.TestCase):
    def test_login_annotation_export_and_stale_review(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            store = Store(path/'test.sqlite3')
            save_restaurant(store, {'data_id':'r1','title':'Quán A','rating':4.5}, '2026-09-17T00:00:00+00:00')
            save_reviews(store, 'r1', [{'review_id':'v1','snippet':'Món ăn ngon','rating':5}],
                         '2026-09-17T00:00:00+00:00')
            app = create_app({'TESTING':True,'DATABASE':str(store.path),
                              'MODEL_PATH':str(path/'missing.joblib')})
            client = app.test_client()
            self.assertEqual(client.get('/admin/').status_code, 302)
            self.assertEqual(client.get('/admin/export').status_code, 302)
            client.get('/login')
            with client.session_transaction() as state: csrf = state['csrf']
            self.assertEqual(client.post('/login', data={'csrf':csrf,'username':'admin',
                                                               'password':'wrong'}).status_code, 200)
            response = client.post('/login', data={'csrf':csrf,'username':'admin',
                                                          'password':'admin'}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            response = client.get('/admin/')
            self.assertIn('Món ăn ngon'.encode(), response.data)
            with client.session_transaction() as state: csrf = state['csrf']
            form = {'csrf':csrf,'restaurant_id':'r1','review_id':'v1',
                    'text_hash':text_hash('Món ăn ngon'),'labels':['food:POSITIVE']}
            self.assertEqual(client.post('/admin/save', data=form).status_code, 302)
            records = json.loads(client.get('/admin/export').data)['records']
            self.assertEqual(records[0]['labels'], ['food:POSITIVE'])
            with store.connect() as db:
                db.execute("UPDATE reviews SET text='Món ăn đã đổi' WHERE restaurant_id='r1' AND id='v1'")
            self.assertEqual(json.loads(client.get('/admin/export').data)['records'], [])
            self.assertEqual(client.post('/admin/save', data=form).status_code, 302)
            with store.connect() as db:
                labels = db.execute("SELECT labels_json FROM gold_annotations WHERE review_id='v1'").fetchone()[0]
            self.assertEqual(json.loads(labels), ['food:POSITIVE'])
            self.assertEqual(client.post('/logout', data={'csrf':csrf}).status_code, 302)
            self.assertEqual(client.get('/admin/').status_code, 302)


if __name__ == '__main__': unittest.main()
