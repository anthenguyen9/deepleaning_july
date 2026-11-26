"""SQLite accounts, registration, login and per-account preferences."""
import sqlite3

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from pipeline import ASPECTS
from storage import utcnow


def init_auth(app, store):
    previous_profile=store.profile()
    previous_memory=store.memory()
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','user')),
            name TEXT NOT NULL,area TEXT NOT NULL,cuisine TEXT NOT NULL,
            min_rating REAL NOT NULL,aspect TEXT NOT NULL,explicit_notes TEXT NOT NULL,
            learned_summary TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS user_feedback (
            user_id INTEGER NOT NULL REFERENCES accounts(id),
            restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
            signal TEXT NOT NULL CHECK(signal IN ('like','dislike')),
            note TEXT NOT NULL,updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id,restaurant_id))''')
        db.execute('''CREATE TABLE IF NOT EXISTS user_searches (
            search_id INTEGER PRIMARY KEY REFERENCES searches(id),
            user_id INTEGER NOT NULL REFERENCES accounts(id))''')
        admin_name = app.config['ADMIN_USERNAME']
        existing = db.execute('SELECT id FROM accounts WHERE username=?', (admin_name,)).fetchone()
        if not existing:
            db.execute('''INSERT INTO accounts(username,password_hash,role,name,area,cuisine,
                min_rating,aspect,explicit_notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (admin_name,generate_password_hash(app.config['ADMIN_PASSWORD']),'admin',
                 previous_profile['name'],previous_profile['area'],
                 previous_profile['cuisine'] or 'Món Việt',previous_profile['min_rating'],
                 previous_profile['aspect'],previous_memory['explicit_notes'] or 'Chưa có',utcnow()))

    auth = Blueprint('auth', __name__)

    def profile_fields(form):
        name=form.get('name','').strip();area=form.get('area','').strip()
        cuisine=form.get('cuisine','').strip();notes=form.get('explicit_notes','').strip()
        aspect=form.get('aspect','').strip()
        try: rating=float(form.get('min_rating',''))
        except ValueError: raise ValueError('Điểm tối thiểu không hợp lệ.') from None
        if not (1<=len(name)<=80 and 2<=len(area)<=160 and 1<=len(cuisine)<=80
                and 1<=len(notes)<=800 and aspect in ASPECTS and 0<=rating<=5):
            raise ValueError('Vui lòng nhập đầy đủ thông tin hồ sơ hợp lệ.')
        return name,area,cuisine,rating,aspect,notes

    @auth.route('/login', methods=['GET','POST'])
    def login():
        if request.method=='POST':
            username=request.form.get('username','').strip()
            password=request.form.get('password','')
            with store.connect() as db:
                row=db.execute('SELECT id,password_hash FROM accounts WHERE username=?',(username,)).fetchone()
            if row and check_password_hash(row['password_hash'],password):
                session.clear();session['user_id']=row['id']
                return redirect(url_for('home'))
            flash('Tài khoản hoặc mật khẩu không đúng.','error')
        return render_template('login.html')

    @auth.route('/register', methods=['GET','POST'])
    def register():
        if request.method=='POST':
            username=request.form.get('username','').strip()
            password=request.form.get('password','')
            try:
                fields=profile_fields(request.form)
                if not (3<=len(username)<=40 and username.isascii() and
                        all(c.isalnum() or c in '._-' for c in username)):
                    raise ValueError('Tên đăng nhập cần 3–40 ký tự chữ, số, dấu chấm, gạch nối hoặc gạch dưới.')
                if len(password)<8 or len(password)>128 or password!=request.form.get('confirm_password'):
                    raise ValueError('Mật khẩu cần ít nhất 8 ký tự và hai ô mật khẩu phải khớp.')
                with store.connect() as db:
                    uid=db.execute('''INSERT INTO accounts(username,password_hash,role,name,area,cuisine,
                        min_rating,aspect,explicit_notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                        (username,generate_password_hash(password),'user',*fields,utcnow())).lastrowid
                session.clear();session['user_id']=uid
                return redirect(url_for('home'))
            except sqlite3.IntegrityError:
                flash('Tên đăng nhập đã được dùng.','error')
            except ValueError as error:
                flash(str(error),'error')
        return render_template('register.html')

    @auth.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('auth.login'))

    @auth.route('/profile', methods=['GET','POST'])
    def profile():
        if g.user is None: return redirect(url_for('auth.login'))
        if request.method=='POST':
            try:
                fields=profile_fields(request.form)
                with store.connect() as db:
                    db.execute('''UPDATE accounts SET name=?,area=?,cuisine=?,min_rating=?,aspect=?,
                        explicit_notes=? WHERE id=?''',(*fields,g.user['id']))
                flash('Đã lưu hồ sơ.','success')
                return redirect(url_for('auth.profile'))
            except ValueError as error: flash(str(error),'error')
        return render_template('profile.html',feedback_items=feedback(store))

    app.register_blueprint(auth)


def load_user(store):
    uid=session.get('user_id')
    with store.connect() as db:
        row=db.execute('''SELECT id,username,role,name,area,cuisine,min_rating,aspect,
            explicit_notes,learned_summary FROM accounts WHERE id=?''',(uid,)).fetchone() if uid else None
    g.user=dict(row) if row else None
    if uid and row is None: session.clear()


def require_admin():
    if g.user is None:
        return redirect(url_for('auth.login'))
    if g.user['role'] != 'admin': abort(403)
    return None


def user_profile():
    return {k:g.user[k] for k in ('name','area','cuisine','min_rating','aspect')}


def user_memory():
    return {'explicit_notes':g.user['explicit_notes'],'learned_summary':g.user['learned_summary']}


def feedback(store):
    with store.connect() as db:
        return [dict(row) for row in db.execute('''SELECT f.*,r.name,r.category,r.price FROM user_feedback f
            JOIN restaurants r ON r.id=f.restaurant_id WHERE f.user_id=? ORDER BY f.updated_at DESC''',(g.user['id'],))]


def save_feedback(store,restaurant_id,signal,note):
    with store.connect() as db:
        if signal=='clear':
            db.execute('DELETE FROM user_feedback WHERE user_id=? AND restaurant_id=?',(g.user['id'],restaurant_id))
        else:
            db.execute('''INSERT INTO user_feedback VALUES(?,?,?,?,?) ON CONFLICT(user_id,restaurant_id)
                DO UPDATE SET signal=excluded.signal,note=excluded.note,updated_at=excluded.updated_at''',
                (g.user['id'],restaurant_id,signal,note,utcnow()))


def own_search(store,sid):
    with store.connect() as db:
        db.execute('INSERT INTO user_searches VALUES(?,?)',(sid,g.user['id']))


def get_search(store,sid):
    with store.connect() as db:
        owner=db.execute('SELECT user_id FROM user_searches WHERE search_id=?',(sid,)).fetchone()
    if owner is None:
        return store.get_search(sid) if g.user['role']=='admin' else None
    return store.get_search(sid) if owner['user_id']==g.user['id'] or g.user['role']=='admin' else None


def history(store):
    with store.connect() as db:
        if g.user['role']=='admin':
            return [dict(r) for r in db.execute('SELECT id,area,query,created_at,status FROM searches ORDER BY id DESC LIMIT 30')]
        return [dict(r) for r in db.execute('''SELECT s.id,s.area,s.query,s.created_at,s.status
            FROM searches s JOIN user_searches u ON u.search_id=s.id WHERE u.user_id=?
            ORDER BY s.id DESC LIMIT 30''',(g.user['id'],))]
