"""Admin-only location selection and crawl controls."""
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from auth import require_admin
from assistant_service import crawl_or_reuse
from locations import children, lineage, place
from restaurant_service import ApiError, SerpClient


def register_location_routes(app,store,analyzer,client_factory):
    bp=Blueprint('locations',__name__,url_prefix='/admin/locations')

    @bp.get('/')
    def index():
        guard=require_admin()
        if guard: return guard
        try: lid=int(request.args.get('location_id','0'))
        except ValueError: abort(400)
        selected=place(store,lid) if lid else None
        if lid and not selected: abort(404)
        with store.connect() as db:
            if selected:
                count=db.execute('''SELECT COUNT(DISTINCT r.id),COUNT(DISTINCT v.restaurant_id||':'||v.id)
                    FROM restaurant_locations l JOIN restaurants r ON r.id=l.restaurant_id
                    LEFT JOIN reviews v ON v.restaurant_id=r.id WHERE l.location_id=?''',(lid,)).fetchone()
                run=db.execute('''SELECT * FROM crawl_runs WHERE location_id=? ORDER BY started_at DESC LIMIT 1''',
                               (lid,)).fetchone()
            else: count=(0,0);run=None
        return render_template('admin_locations.html',countries=children(store),selected=selected,
                               lineage=lineage(store,lid) if selected else [],
                               stats={'restaurants':count[0],'reviews':count[1]},run=dict(run) if run else None)

    @bp.get('/api/children')
    def api_children():
        guard=require_admin()
        if guard: return guard
        try: parent=int(request.args.get('parent','0'))
        except ValueError: abort(400)
        if not place(store,parent): abort(404)
        return jsonify(children(store,parent))

    @bp.post('/crawl')
    def crawl():
        guard=require_admin()
        if guard: return guard
        try: lid=int(request.form.get('location_id','0'))
        except ValueError: abort(400)
        selected=place(store,lid)
        cuisine=' '.join(request.form.get('cuisine','').split())
        if not selected or selected['level']=='country' or len(cuisine)>80: abort(400)
        try:
            factory=client_factory or (lambda s: SerpClient(s,daily_limit=app.config['DAILY_LIMIT']))
            sid,reused=crawl_or_reuse(store,factory(store),analyzer,selected,cuisine)
            flash('Đã dùng dữ liệu crawl trong tháng.' if reused else 'Đã cập nhật nhà hàng và review.','success')
            return redirect(url_for('results',sid=sid))
        except ApiError as exc:
            flash(str(exc),'error')
            return redirect(url_for('locations.index',location_id=lid))

    app.register_blueprint(bp)
