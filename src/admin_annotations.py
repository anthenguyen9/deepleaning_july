"""Local admin review annotation, kept separate from model predictions."""
import hashlib
import io
import json
from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, session, url_for

from pipeline import ASPECTS, CLASSES, POLARITIES
from auth import require_admin


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def register_admin(app, store):
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS gold_annotations (
            restaurant_id TEXT NOT NULL, review_id TEXT NOT NULL,
            text_hash TEXT NOT NULL, labels_json TEXT NOT NULL,
            annotator TEXT NOT NULL, reviewed_at TEXT NOT NULL,
            PRIMARY KEY (restaurant_id, review_id),
            FOREIGN KEY (restaurant_id, review_id) REFERENCES reviews(restaurant_id, id))''')

    admin = Blueprint('admin', __name__, url_prefix='/admin')

    @admin.get('/login')
    def old_login():
        return redirect(url_for('auth.login'))

    @admin.get('/')
    def index():
        guard = require_admin()
        if guard: return guard
        try: page = max(1, int(request.args.get('page', '1')))
        except ValueError: abort(400)
        if page > 100000: abort(400)
        with store.connect() as db:
            total = db.execute("SELECT COUNT(*) FROM reviews WHERE trim(text)<>''").fetchone()[0]
            reviewed = db.execute('''SELECT COUNT(*) FROM reviews v JOIN gold_annotations a
                ON a.restaurant_id=v.restaurant_id AND a.review_id=v.id
                WHERE trim(v.text)<>'' AND a.text_hash IS NOT NULL''').fetchone()[0]
            automatic = db.execute("SELECT COUNT(*) FROM gold_annotations WHERE annotator LIKE 'ai:%'").fetchone()[0]
            rows = [dict(row) for row in db.execute('''SELECT v.restaurant_id,v.id,v.text,v.rating,
                v.published_at,r.name AS restaurant_name,a.text_hash,a.labels_json,a.annotator
                FROM reviews v JOIN restaurants r ON r.id=v.restaurant_id
                LEFT JOIN gold_annotations a ON a.restaurant_id=v.restaurant_id AND a.review_id=v.id
                WHERE trim(v.text)<>'' ORDER BY v.restaurant_id,v.id LIMIT 20 OFFSET ?''', ((page-1)*20,))]
        for row in rows:
            row['current_hash'] = text_hash(row['text'])
            row['current'] = row['text_hash'] == row['current_hash']
            row['labels'] = json.loads(row['labels_json']) if row['current'] and row['labels_json'] else []
        return render_template('admin_annotations.html', rows=rows, total=total, reviewed=reviewed,
                               automatic=automatic,
                               page=page, pages=max(1, (total+19)//20), aspects=ASPECTS,
                               polarities=POLARITIES)

    @admin.post('/save')
    def save():
        guard = require_admin()
        if guard: return guard
        restaurant_id = request.form.get('restaurant_id', '')
        review_id = request.form.get('review_id', '')
        labels = request.form.getlist('labels')
        if not restaurant_id or not review_id or len(labels) != len(set(labels)) or any(label not in CLASSES for label in labels):
            abort(400)
        with store.connect() as db:
            row = db.execute("SELECT text FROM reviews WHERE restaurant_id=? AND id=? AND trim(text)<>''",
                             (restaurant_id, review_id)).fetchone()
            if row is None: abort(404)
            digest = text_hash(row['text'])
            if request.form.get('text_hash') != digest:
                flash('Review đã thay đổi; tải lại trang trước khi gán nhãn.', 'error')
                return redirect(url_for('admin.index'))
            db.execute('''INSERT INTO gold_annotations VALUES(?,?,?,?,?,?)
                ON CONFLICT(restaurant_id,review_id) DO UPDATE SET
                text_hash=excluded.text_hash,labels_json=excluded.labels_json,
                annotator=excluded.annotator,reviewed_at=excluded.reviewed_at''',
                (restaurant_id, review_id, digest, json.dumps(sorted(labels)),
                 app.config['ADMIN_USERNAME'], datetime.now(timezone.utc).isoformat()))
        flash('Đã lưu nhãn gold cho review.', 'success')
        try: page = max(1, int(request.form.get('page', '1')))
        except ValueError: page = 1
        return redirect(url_for('admin.index', page=page))

    @admin.get('/export')
    def export():
        guard = require_admin()
        if guard: return guard
        with store.connect() as db:
            rows = [dict(row) for row in db.execute('''SELECT v.restaurant_id,v.id AS review_id,
                v.text,v.published_at,v.rating,a.text_hash,a.labels_json,a.annotator
                FROM gold_annotations a JOIN reviews v
                ON v.restaurant_id=a.restaurant_id AND v.id=a.review_id
                ORDER BY v.restaurant_id,v.id''')]
        records = [{'restaurant_id':r['restaurant_id'],'review_id':r['review_id'],
                    'text':r['text'],'published_at':r['published_at'],'rating':r['rating'],
                    'labels':json.loads(r['labels_json']),'annotator':r['annotator'],
                    'reviewed':not r['annotator'].startswith('ai:'),
                    'annotation_origin':'ai' if r['annotator'].startswith('ai:') else 'human'}
                   for r in rows if r['text_hash'] == text_hash(r['text'])]
        content = json.dumps({'source':'admin_annotations_mixed_provenance','records':records}, ensure_ascii=False, indent=2)
        return send_file(io.BytesIO(content.encode('utf-8')), mimetype='application/json',
                         as_attachment=True, download_name='gold_annotations.json')

    app.register_blueprint(admin)
