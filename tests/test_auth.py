import tempfile
import unittest
from pathlib import Path

from webapp import create_app


class AccountTests(unittest.TestCase):
    def test_registration_profile_role_and_search_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            app=create_app({'TESTING':True,'DATABASE':str(Path(temp)/'app.sqlite3'),
                            'MODEL_PATH':str(Path(temp)/'missing.joblib')})
            store=app.extensions['store']
            one=app.test_client()
            self.assertEqual(one.get('/').headers['Location'],'/login')
            self.assertEqual(one.get('/admin/').headers['Location'],'/login')
            one.get('/register')
            with one.session_transaction() as state: csrf=state['csrf']
            form={'csrf':csrf,'username':'alice','password':'password123',
                  'confirm_password':'password123','name':'Alice','area':'Hải Châu',
                  'cuisine':'Món Việt','explicit_notes':'Thích quán yên tĩnh',
                  'aspect':'food','min_rating':'3.5'}
            incomplete=dict(form);incomplete.pop('cuisine')
            self.assertEqual(one.post('/register',data=incomplete).status_code,200)
            self.assertEqual(one.post('/register',data=form).headers['Location'],'/')
            with store.connect() as db:
                account=db.execute("SELECT * FROM accounts WHERE username='alice'").fetchone()
                self.assertEqual(account['role'],'user')
                self.assertNotIn('password123',account['password_hash'])
                sid=db.execute("INSERT INTO searches(area,query,created_at,status,result) VALUES(?,?,?,?,?)",
                               ('Hải Châu','test','2026-09-17','success','{"restaurants":[],"calls":0,"cache_hits":0,"warnings":[]}')).lastrowid
                db.execute('INSERT INTO user_searches VALUES(?,?)',(sid,account['id']))
            self.assertEqual(one.get('/admin/').status_code,403)
            self.assertEqual(one.get('/admin/export').status_code,403)
            self.assertEqual(one.get(f'/results/{sid}').status_code,200)
            with one.session_transaction() as state: csrf=state['csrf']
            update={'csrf':csrf,'name':'Alice New','area':'Sơn Trà','cuisine':'Hải sản',
                    'explicit_notes':'Thích vị cay','aspect':'service','min_rating':'4'}
            self.assertEqual(one.post('/profile',data=update).status_code,302)
            self.assertIn('Alice New'.encode(),one.get('/profile').data)
            self.assertEqual(one.post('/logout',data={'csrf':csrf}).status_code,302)
            self.assertEqual(one.get('/profile').headers['Location'],'/login')
            second=app.test_client();second.get('/register')
            with second.session_transaction() as state: other_csrf=state['csrf']
            other=dict(form,csrf=other_csrf,username='bob',name='Bob')
            second.post('/register',data=other)
            self.assertEqual(second.get(f'/results/{sid}').status_code,404)
            self.assertNotIn(b'class="history"',second.get('/').data)


if __name__=='__main__': unittest.main()
