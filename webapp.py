import os
import json
import hashlib
import secrets
import threading
import time
from pathlib import Path
from flask import Flask, Response, abort, flash, g, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
from storage import Store, utcnow
from restaurant_service import Analyzer, ApiError, SerpClient
from gemini_service import GeminiClient, GeminiError, evidence_fallback, restaurant_context, reply_language_for
from pipeline import ASPECTS
from retrieval_service import retrieve
from recommendation_service import rank_restaurants
from data_pipeline import build_index, compute_trends, status
import auth
from chat_ui import assistant_reply, review_url
from assistant_service import crawl_or_reuse, ensure_history_table, history as assistant_history, recommend, save_turn
from assistant_view import build_assistant_view
from trend_dashboard import build_dashboard
from locations import lineage, resolve, resolve_area_text

ROOT=Path(__file__).resolve().parent
LABELS={'food':'Món ăn','price':'Giá cả','service':'Phục vụ','ambience':'Không gian','location':'Vị trí'}

def session_secret():
    configured=os.getenv('FLASK_SECRET_KEY','').strip()
    if configured: return configured
    path=ROOT/'instance'/'.flask_secret_key'
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('x',encoding='ascii') as handle:
            handle.write(secrets.token_urlsafe(48))
    except FileExistsError:
        pass
    for _ in range(20):
        value=path.read_text(encoding='ascii').strip()
        if len(value)>=32: return value
        time.sleep(0.05)
    raise RuntimeError('Không đọc được khóa phiên cục bộ trong instance/.flask_secret_key.')

def create_app(config=None, client_factory=None, gemini_factory=None):
    load_dotenv(ROOT/'.env')
    public=os.getenv('DEPLOYMENT_MODE','').lower()=='public'
    # Demo access applies only to the published instance. Local login keeps
    # the existing account/session flow even if demo variables are present.
    demo_access_password=os.getenv('DEMO_ACCESS_PASSWORD','') if public else ''
    demo_auto_username=os.getenv('DEMO_AUTO_LOGIN_USERNAME','').strip() if public else ''
    if demo_auto_username and not demo_access_password:
        raise RuntimeError('Demo auto-login requires DEMO_ACCESS_PASSWORD.')
    public_hosts=[h.strip() for h in os.getenv('PUBLIC_HOSTS',os.getenv('RAILWAY_PUBLIC_DOMAIN','')).split(',') if h.strip()] if public else []
    if public:
        if len(os.getenv('FLASK_SECRET_KEY','').strip())<32:
            raise RuntimeError('Public deployment requires FLASK_SECRET_KEY (at least 32 characters).')
        password=os.getenv('ADMIN_PASSWORD','')
        if len(password)<16 or password in {'admin','change-this-before-first-run'}:
            raise RuntimeError('Public deployment requires a unique ADMIN_PASSWORD (at least 16 characters).')
        if not public_hosts:
            raise RuntimeError('Public deployment requires PUBLIC_HOSTS or RAILWAY_PUBLIC_DOMAIN.')
    app=Flask(__name__)
    app.config.update(SECRET_KEY=session_secret(),
        SESSION_COOKIE_NAME='foodlens_'+hashlib.sha256(str(ROOT).encode()).hexdigest()[:12],
        ADMIN_USERNAME=os.getenv('ADMIN_USERNAME','admin'),ADMIN_PASSWORD=os.getenv('ADMIN_PASSWORD','admin'),
        RETRIEVAL_METHOD=os.getenv('RETRIEVAL_METHOD','hybrid'),
        DATABASE=os.getenv('DATABASE_PATH',str(ROOT/'instance'/'food_reviews.sqlite3')),
        AUTO_BUILD_DENSE=os.getenv('AUTO_BUILD_DENSE','0')=='1',
        MODEL_PATH=os.getenv('MODEL_PATH',str(ROOT/'outputs'/'baseline.joblib')),MAX_CONTENT_LENGTH=16384,
        SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',
        SESSION_COOKIE_SECURE=public,
        TRUSTED_HOSTS=['localhost','127.0.0.1']+public_hosts,
        DAILY_LIMIT=int(os.getenv('SERPAPI_DAILY_LIMIT','30')))
    if config: app.config.update(config)
    app.jinja_env.filters['assistant_reply']=assistant_reply
    app.jinja_env.filters['review_url']=review_url
    store=Store(app.config['DATABASE'])
    analyzer=Analyzer(app.config['MODEL_PATH'])
    lock=threading.Lock()
    app.extensions['store']=store
    auth.init_auth(app,store)
    demo_user_id=None
    if demo_auto_username:
        with store.connect() as db:
            demo_account=db.execute('SELECT id,role FROM accounts WHERE username=?',
                                    (demo_auto_username,)).fetchone()
        if not demo_account or demo_account['role']!='user':
            raise RuntimeError('DEMO_AUTO_LOGIN_USERNAME must name an existing user account.')
        demo_user_id=demo_account['id']
    ensure_history_table(store)
    from admin_annotations import register_admin
    register_admin(app,store)
    from location_routes import register_location_routes
    register_location_routes(app,store,analyzer,client_factory)

    @app.before_request
    def csrf():
        if demo_access_password:
            credentials=request.authorization
            if not (credentials and secrets.compare_digest(credentials.username or '','foodlens')
                    and secrets.compare_digest(credentials.password or '',demo_access_password)):
                return Response('Authentication required',401,
                                {'WWW-Authenticate':'Basic realm="FoodLens Demo"'})
        if demo_user_id is not None:
            if session.get('user_id') != demo_user_id:
                session.pop('_flashes',None)
            session['user_id']=demo_user_id
            if request.endpoint in {'auth.login','auth.register'}:
                return redirect(url_for('assistant_page'))
        auth.load_user(store)
        if 'csrf' not in session: session['csrf']=secrets.token_hex(32)
        if request.method=='POST' and not secrets.compare_digest(session['csrf'], request.form.get('csrf','')):
            session['csrf']=secrets.token_hex(32)
            flash('Phiên biểu mẫu đã hết hạn. Vui lòng gửi lại sau khi trang tải lại.','error')
            target='auth.login' if g.user is None else ('assistant_page' if request.path=='/assistant' else 'home')
            return redirect(url_for(target),code=303)
        if request.endpoint is None: return None
        if request.endpoint not in {'auth.login','auth.register','static','health'} and g.user is None:
            return redirect(url_for('auth.login'))

    @app.get('/health')
    def health():
        with store.connect() as db:
            db.execute('SELECT 1').fetchone()
        return {'status':'ok'}

    @app.after_request
    def headers(response):
        image_sources="'self' data: https://serpapi.com https://tile.openstreetmap.org" if request.path in {'/assistant','/research'} else "'self' data:"
        response.headers['Content-Security-Policy']=("default-src 'self'; style-src 'self'; "
            f"img-src {image_sources}; script-src 'self'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'self'")
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='strict-origin-when-cross-origin' if request.path=='/assistant' else 'no-referrer'
        response.headers['Cache-Control']='no-store'
        return response

    @app.context_processor
    def context(): return {'profile':auth.user_profile() if g.user else {'name':'Khách'},
        'memory':auth.user_memory() if g.user else {},'current_user':g.user,'aspect_names':LABELS,
        'model_ready':analyzer.bundle is not None,'gemini_ready':bool(os.getenv('GEMINI_API_KEY','').strip()),
        'feedback_count':len(auth.feedback(store)) if g.user else 0}

    @app.get('/')
    def home(): return render_template('home.html',history=auth.history(store))

    @app.get('/assistant')
    def assistant_page():
        messages=assistant_history(store,g.user['id'])
        view=build_assistant_view(store,analyzer,messages,auth.user_profile(),
                                  auth.user_memory(),auth.feedback(store))
        return render_template('assistant.html',messages=messages,view=view,assistant_shell=True)

    @app.post('/assistant')
    def assistant_send():
        message=request.form.get('message','').strip()
        english=reply_language_for(message)=='en'
        if not message or len(message)>1200:
            flash('Please enter a message between 1 and 1,200 characters.' if english else
                  'Tin nhắn phải có từ 1 đến 1.200 ký tự.','error')
            return redirect(url_for('assistant_page'))
        past=assistant_history(store,g.user['id'])
        context={}
        reply=''
        try:
            gemini=gemini_factory() if gemini_factory else GeminiClient()
            parsed=gemini.extract_query(message,past,g.user['area'])
            context['extraction']=parsed
            if parsed['intent']!='restaurant_recommendation':
                reply=('I can recommend restaurants. What cuisine and area are you interested in?' if english else
                       'Mình có thể gợi ý nhà hàng. Bạn muốn tìm món gì và ở khu vực nào?')
            else:
                selected=resolve(store,city=parsed['city'] or g.user['area'],
                                 district=parsed['district'],ward=parsed['ward'],street=parsed['street'])
                if not selected:
                    reply=('I could not find that area in the available location data. Please try another city, ward, or street.'
                           if english else 'Không tìm thấy khu vực này trong dữ liệu địa điểm hiện có. Vui lòng cho biết tên thành phố, phường hoặc đường khác.')
                    context['location_valid']=False
                else:
                    context['location_valid']=True
                    context['location_id']=selected['id']
                    context['location']=' › '.join(x['name'] for x in lineage(store,selected['id']))
                    try:
                        client=client_factory(store) if client_factory else SerpClient(store,daily_limit=app.config['DAILY_LIMIT'])
                        sid,reused=crawl_or_reuse(store,client,analyzer,selected,parsed['cuisine'])
                        context['crawl']='cached' if reused else 'refreshed'
                        context['search_id']=sid
                        build_index(store,analyzer.version)
                    except ApiError as exc:
                        context['crawl']='unavailable'
                        context['crawl_error']=str(exc)
                    items=recommend(store,analyzer,auth.user_profile(),auth.user_memory(),
                                    auth.feedback(store),selected,parsed['cuisine'])
                    if not items:
                        reply=('I do not have enough restaurant and review evidence in this area to make a grounded recommendation.'
                               if english else 'Chưa có đủ nhà hàng và review phù hợp ở khu vực này để gợi ý có căn cứ.')
                    else:
                        retrieval=retrieve(store,message,[x['id'] for x in items],limit=12,
                                           method=app.config['RETRIEVAL_METHOD'],fallback=True)
                        hits={}
                        for hit in retrieval['results']:
                            hits.setdefault(hit['restaurant_id'],[]).append({
                                'id':hit['metadata']['review_id'],'text':hit['text'],
                                'rating':hit['metadata'].get('rating'),
                                'published_at':hit['metadata'].get('published_at'),
                                'source_url':hit['metadata'].get('source_url',''),
                                'labels':hit['metadata'].get('labels',[])})
                        grounded=[{**x,'assessment':{**x['assessment'],
                                    'evidence':hits.get(x['id'],x['assessment']['evidence'])}}
                                  for x in items]
                        try:
                            result=gemini.advise({**auth.user_profile(),'area':context['location'],
                                                  'cuisine':parsed['cuisine'] or g.user['cuisine']},
                                                 auth.user_memory(),auth.feedback(store),past,
                                                 grounded,message,reply_language='auto')
                        except GeminiError as exc:
                            app.logger.warning('Gemini advice unavailable: %s',exc)
                            fallback,sources=evidence_fallback(restaurant_context(grounded),
                                                               'en' if english else 'vi')
                            if not sources: raise
                            note=('Gemini is unavailable right now. Here are reviews from the saved data instead.\n\n'
                                  if english else 'Gemini hiện không phản hồi. Dưới đây là review từ dữ liệu đã lưu để bạn tham khảo.\n\n')
                            reply=note+fallback
                            context.update(candidate_ids=[x['id'] for x in grounded[:5]],
                                           recommended_restaurant_ids=[],citations=sources,
                                           citation_status='local_evidence',
                                           abstention_reason='gemini_unavailable',
                                           retrieval_method=retrieval['method'])
                        else:
                            reply=result['reply']
                            context.update(candidate_ids=result['candidate_ids'],
                                           recommended_restaurant_ids=result['recommended_restaurant_ids'],
                                           citations=result.get('citation_sources',[]),
                                           citation_status=result.get('citation_status'),
                                           abstention_reason=result.get('abstention_reason'),
                                           citation_attempts=result.get('citation_attempts',1),
                                           retrieval_method=retrieval['method'])
        except GeminiError as exc:
            reason=str(exc)
            app.logger.warning('Gemini assistant unavailable: %s',reason)
            if 'giới hạn' in reason:
                reply=('Gemini has reached its usage limit. Please try again later.' if english else
                       'Gemini đã đạt giới hạn sử dụng. Vui lòng thử lại sau.')
            elif 'HTTP 503' in reason:
                reply=('Gemini is temporarily busy (HTTP 503). Please retry shortly.' if english else
                       'Gemini đang tạm thời quá tải (HTTP 503). Vui lòng thử lại sau ít phút.')
            elif 'GEMINI_API_KEY' in reason or 'API key' in reason:
                reply=('Gemini is not configured or its API key is invalid. Please check the server configuration.'
                       if english else 'Gemini chưa được cấu hình hoặc API key không hợp lệ. Vui lòng kiểm tra cấu hình máy chủ.')
            else:
                reply=('The assistant is temporarily unavailable. Please try again.' if english else
                       'Trợ lý tạm thời không khả dụng. Vui lòng thử lại.')
            context['error']='gemini'
        except (ValueError,RuntimeError,OSError) as exc:
            reply=('I could not complete this request right now. Please try again.' if english else
                   'Không thể hoàn thành yêu cầu lúc này. Vui lòng thử lại.')
            context['error']=type(exc).__name__
        save_turn(store,g.user['id'],message,reply,context)
        return redirect(url_for('assistant_page'))

    @app.get('/research')
    def research_dashboard():
        granularity=request.args.get('granularity','month')
        if granularity not in {'day','month','year'}: abort(400)
        aspect=request.args.get('aspect','food')
        if aspect not in LABELS: abort(400)
        year=request.args.get('year','all')
        area=request.args.get('area','all')
        if area!='all' and not area.isdecimal(): abort(400)
        area_id=int(area) if area!='all' else None
        dashboard=build_dashboard(store,granularity,year,area_id,aspect)
        if year!='all' and year not in dashboard['years']: abort(400)
        if area_id is not None and area_id not in {row['id'] for row in dashboard['areas']}: abort(400)
        with store.connect() as db:
            quota=db.execute("SELECT COUNT(*) FROM api_calls WHERE created_at>=date('now')").fetchone()[0]
        return render_template('research.html',stats=status(store),dashboard=dashboard,
            granularity=granularity,year=year,area=area,aspect=aspect,
            quota=quota,daily_limit=app.config['DAILY_LIMIT'],method=app.config['RETRIEVAL_METHOD'])

    @app.post('/search')
    def search():
        area=' '.join(request.form.get('area','').split())
        try:
            limit=int(request.form.get('limit','3'));pages=int(request.form.get('pages','1'))
            if not 2<=len(area)<=160 or not 1<=limit<=5 or not 1<=pages<=3: raise ValueError()
        except ValueError:
            flash('Nhập khu vực 2–160 ký tự, 1–5 nhà hàng và 1–3 trang review.','error')
            return redirect(url_for('home'))
        selected=resolve_area_text(store,area)
        if not selected:
            flash('Khu vực chưa có trong dữ liệu địa điểm. Nhập Đà Nẵng hoặc tên phường/đường, Đà Nẵng.','error')
            return redirect(url_for('home'))
        if not lock.acquire(blocking=False):
            flash('Một lượt tìm kiếm đang chạy. Vui lòng chờ hoàn tất.','error')
            return redirect(url_for('home'))
        try:
            client=client_factory(store) if client_factory else SerpClient(store,daily_limit=app.config['DAILY_LIMIT'])
            sid,reused=crawl_or_reuse(store,client,analyzer,selected,g.user['cuisine'],limit,pages)
            if reused:
                cached=store.get_search(sid)
                with store.connect() as db:
                    sid=db.execute('INSERT INTO searches(area,query,created_at,status,result) VALUES(?,?,?,?,?)',
                        (cached['area'],cached['query'],utcnow(),cached['status'],
                         json.dumps(cached['result'],ensure_ascii=False))).lastrowid
            auth.own_search(store,sid)
            build_index(store,analyzer.version)
            if app.config['AUTO_BUILD_DENSE'] and not app.config['TESTING'] and app.config['RETRIEVAL_METHOD'] in {'dense','hybrid'}:
                try:
                    from dense_service import build_dense
                    build_dense(store)
                except (ImportError,OSError,RuntimeError,ValueError):
                    flash('Chỉ mục ngữ nghĩa chưa sẵn sàng; chatbot sẽ dùng BM25.','error')
            compute_trends(store,analyzer.version)
            return redirect(url_for('results',sid=sid))
        except ApiError as e:
            flash(str(e),'error');return redirect(url_for('home'))
        finally: lock.release()

    @app.get('/results/<int:sid>')
    def results(sid):
        record=auth.get_search(store,sid)
        if not record: abort(404)
        p=auth.user_profile()
        memory=auth.user_memory(); feedback_rows=auth.feedback(store)
        chat=store.chat(sid)
        recommended=[]
        for message in reversed(chat['messages']):
            if message['role']=='assistant':
                recommended=message['context'].get('recommended_restaurant_ids',[]);break
        all_items=record['result']['restaurants']
        items=[x for x in all_items if (x['rating'] or 0)>=p['min_rating']]
        items=rank_restaurants(items,p,memory,feedback_rows,recommended,config='E')
        return render_template('results.html',record=record,items=items,hidden_count=len(all_items)-len(items),chat=chat)

    @app.post('/results/<int:sid>/feedback/<path:restaurant_id>')
    def restaurant_feedback(sid,restaurant_id):
        record=auth.get_search(store,sid)
        if not record: abort(404)
        valid={x['id'] for x in record['result']['restaurants']}
        signal=request.form.get('signal','')
        note=request.form.get('note','').strip()
        if restaurant_id not in valid or signal not in {'like','dislike','clear'} or len(note)>300: abort(400)
        auth.save_feedback(store,restaurant_id,signal,note)
        flash('Đã cập nhật phản hồi để cá nhân hóa các lần gợi ý sau.','success')
        return redirect(url_for('results',sid=sid))

    @app.post('/results/<int:sid>/chat')
    def chat_send(sid):
        record=auth.get_search(store,sid)
        if not record: abort(404)
        message=request.form.get('message','').strip()
        if not message or len(message)>1200:
            flash('Tin nhắn phải có từ 1 đến 1.200 ký tự.','error')
            return redirect(url_for('results',sid=sid,_anchor='chat'))
        chat=store.chat(sid)
        try:
            candidates=[x for x in record['result']['restaurants']
                if (x.get('rating') or 0)>=g.user['min_rating']]
            retrieval=retrieve(store,message,[x['id'] for x in candidates],limit=12,search_id=sid,
                method=app.config['RETRIEVAL_METHOD'],fallback=True)
            grounded=[]
            if retrieval['results']:
                by_restaurant={}
                for hit in retrieval['results']:
                    by_restaurant.setdefault(hit['restaurant_id'],[]).append({
                        'id':hit['metadata']['review_id'],'text':hit['text'],
                        'rating':hit['metadata'].get('rating'),'published_at':hit['metadata'].get('published_at'),
                        'date_text':'','source_url':hit['metadata'].get('source_url',''),
                        'labels':hit['metadata'].get('labels',[]),'retrieval_score':hit['score']})
                for item in candidates:
                    if item['id'] in by_restaurant:
                        clone={**item,'assessment':{**item.get('assessment',{}),'evidence':by_restaurant[item['id']]}}
                        grounded.append(clone)
            else:
                grounded=[]
            advisor=gemini_factory() if gemini_factory else GeminiClient()
            result=advisor.advise(auth.user_profile(),auth.user_memory(),auth.feedback(store),chat['messages'],
                                  grounded,message)
            context={'recommended_restaurant_ids':result['recommended_restaurant_ids'],
                     'candidate_ids':result['candidate_ids'],'citations':result.get('citations',[]),
                     'citation_sources':result.get('citation_sources',[]),
                     'citation_status':result.get('citation_status','unknown'),
                     'abstained':result.get('abstained',False),
                     'abstention_reason':result.get('abstention_reason',''),
                     'retrieval_method':retrieval['method'],
                     'retrieval_fallback':retrieval.get('fallback_reason'),
                     'generation_duration_ms':result.get('duration_ms'),
                     'usage':result.get('usage',{}),
                     'retrieval_result_count':len(retrieval['results']),
                     'retrieval_duration_ms':retrieval['duration_ms']}
            store.add_chat_turn(sid,message,result['reply'],result['model'],context)
            if result['learned_preferences']:
                with store.connect() as db:
                    db.execute('UPDATE accounts SET learned_summary=? WHERE id=?',
                               (result['learned_preferences'],g.user['id']))
        except GeminiError as e: flash(str(e),'error')
        return redirect(url_for('results',sid=sid,_anchor='chat'))

    @app.post('/results/<int:sid>/chat/clear')
    def chat_clear(sid):
        if not auth.get_search(store,sid): abort(404)
        store.clear_chat(sid);flash('Đã xóa lịch sử chat của lượt tìm này.','success')
        return redirect(url_for('results',sid=sid,_anchor='chat'))

    @app.post('/memory/clear')
    def memory_clear():
        with store.connect() as db:
            db.execute("UPDATE accounts SET learned_summary='' WHERE id=?",(g.user['id'],))
            db.execute('DELETE FROM user_feedback WHERE user_id=?',(g.user['id'],))
        flash('Đã xóa sở thích học tự động và phản hồi quán.','success')
        return redirect(url_for('home'))

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('error.html',message='Không thể hoàn thành yêu cầu. Kiểm tra kết nối hoặc khởi động lại ứng dụng.'),500

    return app

if __name__=='__main__':
    from waitress import serve
    host='0.0.0.0' if os.getenv('DEPLOYMENT_MODE','').lower()=='public' else '127.0.0.1'
    port=int(os.getenv('PORT','5000'))
    print(f'Food Review Web: http://{host}:{port} (Ctrl+C to stop)')
    serve(create_app(),host=host,port=port,threads=4)
