"""SQLite persistence for a local, single-user application."""
import json
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS profile (
 id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL, area TEXT NOT NULL,
 cuisine TEXT NOT NULL, min_rating REAL NOT NULL, aspect TEXT NOT NULL);
INSERT OR IGNORE INTO profile VALUES(1,'Người dùng','Đà Nẵng','',0,'food');
CREATE TABLE IF NOT EXISTS restaurants (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, address TEXT, rating REAL, total_reviews INTEGER,
 price TEXT, category TEXT, source_url TEXT, fetched_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews (
 restaurant_id TEXT NOT NULL REFERENCES restaurants(id), id TEXT NOT NULL,
 text TEXT NOT NULL, rating REAL, published_at TEXT, date_text TEXT, source_url TEXT,
 fetched_at TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(restaurant_id,id));
CREATE TABLE IF NOT EXISTS analyses (
 restaurant_id TEXT NOT NULL, review_id TEXT NOT NULL, model_version TEXT NOT NULL,
 text_hash TEXT NOT NULL, labels TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(restaurant_id, review_id, model_version),
 FOREIGN KEY(restaurant_id,review_id) REFERENCES reviews(restaurant_id,id));
CREATE TABLE IF NOT EXISTS searches (
 id INTEGER PRIMARY KEY, area TEXT NOT NULL, query TEXT NOT NULL, created_at TEXT NOT NULL,
 status TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS api_cache (
 cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS api_calls (
 id INTEGER PRIMARY KEY, engine TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preference_memory (
 id INTEGER PRIMARY KEY CHECK(id=1), explicit_notes TEXT NOT NULL,
 learned_summary TEXT NOT NULL, updated_at TEXT NOT NULL);
INSERT OR IGNORE INTO preference_memory VALUES(1,'','','');
CREATE TABLE IF NOT EXISTS restaurant_feedback (
 restaurant_id TEXT PRIMARY KEY REFERENCES restaurants(id),
 signal TEXT NOT NULL CHECK(signal IN ('like','dislike')), note TEXT NOT NULL,
 updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chat_sessions (
 id INTEGER PRIMARY KEY, search_id INTEGER NOT NULL UNIQUE REFERENCES searches(id),
 title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chat_messages (
 id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES chat_sessions(id),
 role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
 model TEXT NOT NULL, context_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id,id);
CREATE TABLE IF NOT EXISTS ingestion_seeds (
 id INTEGER PRIMARY KEY, area TEXT NOT NULL, cuisine TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1, last_run_at TEXT,
 UNIQUE(area,cuisine));
CREATE TABLE IF NOT EXISTS restaurant_crawl_state (
 restaurant_id TEXT PRIMARY KEY REFERENCES restaurants(id), next_page_token TEXT,
 pages_fetched INTEGER NOT NULL DEFAULT 0, review_requests INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','complete','error')),
 last_attempt_at TEXT, last_success_at TEXT, error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS pipeline_jobs (
 id INTEGER PRIMARY KEY, job_type TEXT NOT NULL, parameters TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('running','success','partial','failed')),
 started_at TEXT NOT NULL, finished_at TEXT, stats TEXT NOT NULL DEFAULT '{}',
 error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS dataset_versions (
 id INTEGER PRIMARY KEY, version TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
 restaurant_count INTEGER NOT NULL, review_count INTEGER NOT NULL,
 dated_review_count INTEGER NOT NULL, min_review_date TEXT, max_review_date TEXT,
 source TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS monthly_trends (
 restaurant_id TEXT NOT NULL REFERENCES restaurants(id), month TEXT NOT NULL,
 aspect TEXT NOT NULL, review_count INTEGER NOT NULL, positive_count INTEGER NOT NULL,
 neutral_count INTEGER NOT NULL, negative_count INTEGER NOT NULL,
 average_rating REAL, model_version TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(restaurant_id,month,aspect,model_version));
CREATE TABLE IF NOT EXISTS period_aggregates (
 restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
 granularity TEXT NOT NULL CHECK(granularity IN ('day','month','year')),
 period TEXT NOT NULL, aspect TEXT NOT NULL, review_count INTEGER NOT NULL,
 positive_count INTEGER NOT NULL, neutral_count INTEGER NOT NULL,
 negative_count INTEGER NOT NULL, average_rating REAL,
 model_version TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(restaurant_id,granularity,period,aspect,model_version));
CREATE TABLE IF NOT EXISTS trend_signals (
 restaurant_id TEXT NOT NULL REFERENCES restaurants(id), month TEXT NOT NULL,
 aspect TEXT NOT NULL, review_count INTEGER NOT NULL, volume_change INTEGER,
 average_rating REAL, rating_change REAL, moving_average_rating REAL,
 sentiment_index REAL, sentiment_shift REAL, trend_score REAL,
 signal_level TEXT NOT NULL, sufficient_sample INTEGER NOT NULL,
 model_version TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(restaurant_id,month,aspect,model_version));
CREATE TABLE IF NOT EXISTS evaluation_queries (
 id TEXT PRIMARY KEY, query TEXT NOT NULL, constraints_json TEXT NOT NULL,
 relevant_restaurants_json TEXT NOT NULL, relevant_reviews_json TEXT NOT NULL,
 split TEXT NOT NULL CHECK(split IN ('dev','test')), notes TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS retrieval_events (
 id INTEGER PRIMARY KEY, search_id INTEGER REFERENCES searches(id), query TEXT NOT NULL,
 method TEXT NOT NULL, candidate_restaurants INTEGER NOT NULL, result_count INTEGER NOT NULL,
 result_keys_json TEXT NOT NULL, duration_ms REAL NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_documents (
 document_key TEXT PRIMARY KEY, restaurant_id TEXT NOT NULL, review_id TEXT NOT NULL,
 text TEXT NOT NULL, restaurant_name TEXT NOT NULL, category TEXT NOT NULL,
 metadata_json TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(restaurant_id,review_id) REFERENCES reviews(restaurant_id,id));
CREATE VIRTUAL TABLE IF NOT EXISTS review_fts USING fts5(
 document_key UNINDEXED, text, restaurant_name, category, tokenize='unicode61');
CREATE TABLE IF NOT EXISTS locations (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 normalized_name TEXT NOT NULL, parent_id INTEGER REFERENCES locations(id),
 level TEXT NOT NULL CHECK(level IN ('country','province','district','ward','street')),
 is_active INTEGER NOT NULL DEFAULT 1, effective_from TEXT, effective_to TEXT,
 source TEXT NOT NULL, source_id TEXT, imported_at TEXT NOT NULL,
 UNIQUE(parent_id,level,normalized_name));
CREATE INDEX IF NOT EXISTS idx_locations_parent ON locations(parent_id,level,is_active);
CREATE INDEX IF NOT EXISTS idx_locations_name ON locations(level,normalized_name,is_active);
CREATE TABLE IF NOT EXISTS location_aliases (
 location_id INTEGER NOT NULL REFERENCES locations(id), alias TEXT NOT NULL,
 normalized_alias TEXT NOT NULL, PRIMARY KEY(location_id,normalized_alias));
CREATE INDEX IF NOT EXISTS idx_location_aliases_name ON location_aliases(normalized_alias);
CREATE TABLE IF NOT EXISTS crawl_runs (
 id INTEGER PRIMARY KEY, location_id INTEGER NOT NULL REFERENCES locations(id),
 query TEXT NOT NULL, query_hash TEXT NOT NULL, year_month TEXT NOT NULL,
 provider TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('running','success','failed')),
 started_at TEXT NOT NULL, completed_at TEXT, result_count INTEGER NOT NULL DEFAULT 0,
 error_message TEXT NOT NULL DEFAULT '', search_id INTEGER REFERENCES searches(id),
 UNIQUE(location_id,query_hash,year_month,provider));
CREATE TABLE IF NOT EXISTS restaurant_locations (
 restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
 location_id INTEGER NOT NULL REFERENCES locations(id),
 PRIMARY KEY(restaurant_id,location_id));
CREATE INDEX IF NOT EXISTS idx_restaurant_locations_location ON restaurant_locations(location_id);
CREATE TABLE IF NOT EXISTS gold_annotations (
 restaurant_id TEXT NOT NULL, review_id TEXT NOT NULL, text_hash TEXT NOT NULL,
 labels_json TEXT NOT NULL, annotator TEXT NOT NULL, reviewed_at TEXT NOT NULL,
 PRIMARY KEY(restaurant_id,review_id),
 FOREIGN KEY(restaurant_id,review_id) REFERENCES reviews(restaurant_id,id));
'''

def utcnow():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def profile(self):
        with self.connect() as db:
            return dict(db.execute('SELECT * FROM profile WHERE id=1').fetchone())

    def save_profile(self, name, area, cuisine, min_rating, aspect):
        with self.connect() as db:
            db.execute('UPDATE profile SET name=?,area=?,cuisine=?,min_rating=?,aspect=? WHERE id=1',
                       (name,area,cuisine,min_rating,aspect))

    def memory(self):
        with self.connect() as db:
            row = db.execute('SELECT * FROM preference_memory WHERE id=1').fetchone()
            return dict(row)

    def save_memory(self, explicit_notes=None, learned_summary=None):
        current = self.memory()
        explicit = current['explicit_notes'] if explicit_notes is None else explicit_notes
        learned = current['learned_summary'] if learned_summary is None else learned_summary
        with self.connect() as db:
            db.execute('UPDATE preference_memory SET explicit_notes=?,learned_summary=?,updated_at=? WHERE id=1',
                       (explicit,learned,utcnow()))

    def feedback(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT f.*,r.name,r.category,r.price
                FROM restaurant_feedback f JOIN restaurants r ON r.id=f.restaurant_id
                ORDER BY f.updated_at DESC''')]

    def save_feedback(self, restaurant_id, signal, note=''):
        with self.connect() as db:
            if signal == 'clear':
                db.execute('DELETE FROM restaurant_feedback WHERE restaurant_id=?',(restaurant_id,))
            else:
                db.execute('''INSERT INTO restaurant_feedback VALUES(?,?,?,?)
                    ON CONFLICT(restaurant_id) DO UPDATE SET signal=excluded.signal,
                    note=excluded.note,updated_at=excluded.updated_at''',
                    (restaurant_id,signal,note,utcnow()))

    def ensure_chat(self, search_id):
        with self.connect() as db:
            row=db.execute('SELECT id FROM chat_sessions WHERE search_id=?',(search_id,)).fetchone()
            if row: return row['id']
            stamp=utcnow()
            return db.execute('INSERT INTO chat_sessions(search_id,title,created_at,updated_at) VALUES(?,?,?,?)',
                              (search_id,'Tư vấn nhà hàng',stamp,stamp)).lastrowid

    def chat(self, search_id, limit=20):
        with self.connect() as db:
            session=db.execute('SELECT * FROM chat_sessions WHERE search_id=?',(search_id,)).fetchone()
            if not session: return {'session_id':None,'messages':[]}
            rows=db.execute('''SELECT role,content,model,context_json,created_at FROM
                (SELECT * FROM chat_messages WHERE session_id=? ORDER BY id DESC LIMIT ?)
                ORDER BY id''',(session['id'],limit)).fetchall()
            messages=[]
            for row in rows:
                item=dict(row);item['context']=json.loads(item.pop('context_json'));messages.append(item)
            return {'session_id':session['id'],'messages':messages}

    def add_chat_turn(self, search_id, user_text, assistant_text, model, context):
        session_id=self.ensure_chat(search_id); stamp=utcnow()
        with self.connect() as db:
            db.execute('INSERT INTO chat_messages(session_id,role,content,model,context_json,created_at) VALUES(?,?,?,?,?,?)',
                       (session_id,'user',user_text,'', '{}',stamp))
            db.execute('INSERT INTO chat_messages(session_id,role,content,model,context_json,created_at) VALUES(?,?,?,?,?,?)',
                       (session_id,'assistant',assistant_text,model,json.dumps(context,ensure_ascii=False),stamp))
            db.execute('UPDATE chat_sessions SET updated_at=? WHERE id=?',(stamp,session_id))

    def clear_chat(self, search_id):
        with self.connect() as db:
            row=db.execute('SELECT id FROM chat_sessions WHERE search_id=?',(search_id,)).fetchone()
            if row:
                db.execute('DELETE FROM chat_messages WHERE session_id=?',(row['id'],))
                db.execute('DELETE FROM chat_sessions WHERE id=?',(row['id'],))

    def clear_learned_memory(self):
        with self.connect() as db:
            db.execute("UPDATE preference_memory SET learned_summary='',updated_at=? WHERE id=1",(utcnow(),))
            db.execute('DELETE FROM restaurant_feedback')

    def history(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,area,query,created_at,status FROM searches ORDER BY id DESC LIMIT 30')]

    def get_search(self, search_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM searches WHERE id=?', (search_id,)).fetchone()
            if row:
                item = dict(row)
                item['result'] = json.loads(item['result'])
                return item
