import os
import secrets
import threading
from pathlib import Path
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
from storage import Store
from restaurant_service import Analyzer, ApiError, SerpClient, search_area
from gemini_service import GeminiClient, GeminiError
from pipeline import ASPECTS
from retrieval_service import retrieve
from recommendation_service import rank_restaurants

ROOT=Path(__file__).resolve().parent
LABELS={'food':'Món ăn','price':'Giá cả','service':'Phục vụ','ambience':'Không gian','location':'Vị trí'}

def create_app(config=None, client_factory=None, gemini_factory=None):
    load_dotenv(ROOT/'.env')
    app=Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_hex(32),DATABASE=str(ROOT/'instance'/'food_reviews.sqlite3'),
        MODEL_PATH=str(ROOT/'outputs'/'baseline.joblib'),MAX_CONTENT_LENGTH=16384,
        SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',
        TRUSTED_HOSTS=['localhost','127.0.0.1'],DAILY_LIMIT=int(os.getenv('SERPAPI_DAILY_LIMIT','30')))
    if config: app.config.update(config)
    store=Store(app.config['DATABASE'])
    analyzer=Analyzer(app.config['MODEL_PATH'])
    lock=threading.Lock()
    app.extensions['store']=store

    @app.before_request
    def csrf():
        if 'csrf' not in session: session['csrf']=secrets.token_hex(32)
        if request.method=='POST' and not secrets.compare_digest(session['csrf'], request.form.get('csrf','')):
            abort(400, description='Phiên làm việc hết hạn. Tải lại trang và thử lại.')

    @app.after_request
    def headers(response):
        response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self'; img-src 'self' data:; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        return response

    @app.context_processor
    def context(): return {'profile':store.profile(),'memory':store.memory(),'aspect_names':LABELS,
        'model_ready':analyzer.bundle is not None,'gemini_ready':bool(os.getenv('GEMINI_API_KEY','').strip()),
        'feedback_count':len(store.feedback())}

    @app.get('/')
    def home(): return render_template('home.html',history=store.history())

    @app.post('/profile')
    def profile_save():
        try:
            name=request.form.get('name','').strip(); area=request.form.get('area','').strip()
            cuisine=request.form.get('cuisine','').strip(); aspect=request.form.get('aspect','food')
            notes=request.form.get('explicit_notes','').strip()
            rating=float(request.form.get('min_rating','0'))
            if not name or len(name)>80 or not area or len(area)>160 or len(cuisine)>80 or len(notes)>800 or aspect not in ASPECTS or not 0<=rating<=5:
                raise ValueError()
            store.save_profile(name,area,cuisine,rating,aspect)
            store.save_memory(explicit_notes=notes)
            flash('Đã lưu hồ sơ. Sở thích được áp dụng khi tìm và sắp xếp kết quả.','success')
        except ValueError: flash('Hồ sơ không hợp lệ. Kiểm tra các trường đã nhập.','error')
        return redirect(url_for('home'))

    @app.post('/search')
    def search():
        area=' '.join(request.form.get('area','').split())
        try:
            limit=int(request.form.get('limit','3'));pages=int(request.form.get('pages','1'))
            if not 2<=len(area)<=160 or not 1<=limit<=5 or not 1<=pages<=3: raise ValueError()
        except ValueError:
            flash('Nhập khu vực 2–160 ký tự, 1–5 nhà hàng và 1–3 trang review.','error')
            return redirect(url_for('home'))
        if not lock.acquire(blocking=False):
            flash('Một lượt tìm kiếm đang chạy. Vui lòng chờ hoàn tất.','error')
            return redirect(url_for('home'))
        try:
            client=client_factory(store) if client_factory else SerpClient(store,daily_limit=app.config['DAILY_LIMIT'])
            sid=search_area(store,client,analyzer,area,store.profile()['cuisine'],limit,pages)
            return redirect(url_for('results',sid=sid))
        except ApiError as e:
            flash(str(e),'error');return redirect(url_for('home'))
        finally: lock.release()

    @app.get('/results/<int:sid>')
    def results(sid):
        record=store.get_search(sid)
        if not record: abort(404)
        p=store.profile()
        memory=store.memory(); feedback_rows=store.feedback()
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
        record=store.get_search(sid)
        if not record: abort(404)
        valid={x['id'] for x in record['result']['restaurants']}
        signal=request.form.get('signal','')
        note=request.form.get('note','').strip()
        if restaurant_id not in valid or signal not in {'like','dislike','clear'} or len(note)>300: abort(400)
        store.save_feedback(restaurant_id,signal,note)
        flash('Đã cập nhật phản hồi để cá nhân hóa các lần gợi ý sau.','success')
        return redirect(url_for('results',sid=sid))

    @app.post('/results/<int:sid>/chat')
    def chat_send(sid):
        record=store.get_search(sid)
        if not record: abort(404)
        message=request.form.get('message','').strip()
        if not message or len(message)>1200:
            flash('Tin nhắn phải có từ 1 đến 1.200 ký tự.','error')
            return redirect(url_for('results',sid=sid,_anchor='chat'))
        chat=store.chat(sid)
        try:
            candidates=record['result']['restaurants']
            retrieval=retrieve(store,message,[x['id'] for x in candidates],limit=12,search_id=sid)
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
                grounded=candidates
            advisor=gemini_factory() if gemini_factory else GeminiClient()
            result=advisor.advise(store.profile(),store.memory(),store.feedback(),chat['messages'],
                                  grounded,message)
            context={'recommended_restaurant_ids':result['recommended_restaurant_ids'],
                     'candidate_ids':result['candidate_ids'],'citations':result.get('citations',[]),
                     'citation_sources':result.get('citation_sources',[]),
                     'citation_status':result.get('citation_status','unknown'),
                     'abstained':result.get('abstained',False),
                     'abstention_reason':result.get('abstention_reason',''),
                     'retrieval_method':retrieval['method'] if retrieval['results'] else 'snapshot-fallback',
                     'retrieval_result_count':len(retrieval['results']),
                     'retrieval_duration_ms':retrieval['duration_ms']}
            store.add_chat_turn(sid,message,result['reply'],result['model'],context)
            if result['learned_preferences']:
                store.save_memory(learned_summary=result['learned_preferences'])
        except GeminiError as e: flash(str(e),'error')
        return redirect(url_for('results',sid=sid,_anchor='chat'))

    @app.post('/results/<int:sid>/chat/clear')
    def chat_clear(sid):
        if not store.get_search(sid): abort(404)
        store.clear_chat(sid);flash('Đã xóa lịch sử chat của lượt tìm này.','success')
        return redirect(url_for('results',sid=sid,_anchor='chat'))

    @app.post('/memory/clear')
    def memory_clear():
        store.clear_learned_memory();flash('Đã xóa sở thích học tự động và phản hồi quán.','success')
        return redirect(url_for('home'))

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('error.html',message='Không thể hoàn thành yêu cầu. Kiểm tra kết nối hoặc khởi động lại ứng dụng.'),500

    return app

if __name__=='__main__':
    from waitress import serve
    print('Food Review Web: http://127.0.0.1:5000 (Ctrl+C để dừng)')
    serve(create_app(),host='127.0.0.1',port=5000,threads=4)
