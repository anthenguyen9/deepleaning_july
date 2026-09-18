"""View adapter for the existing assistant, restaurant and review records."""
import json
import re
from urllib.parse import urlsplit

from chat_ui import review_url
from recommendation_service import rank_restaurants


ASPECT_LABELS={'food':'Món ăn','price':'Giá cả','service':'Phục vụ',
               'ambience':'Không gian','location':'Vị trí'}


def _image_url(payload):
    value=payload.get('serpapi_thumbnail','')
    if not isinstance(value,str): return ''
    try: parsed=urlsplit(value)
    except ValueError: return ''
    return value if parsed.scheme=='https' and parsed.hostname=='serpapi.com' else ''


def _coordinates(payload):
    point=payload.get('gps_coordinates') or {}
    try:
        lat=float(point['latitude']);lng=float(point['longitude'])
    except (ValueError,TypeError,KeyError): return None
    return {'lat':lat,'lng':lng} if -90<=lat<=90 and -180<=lng<=180 else None


def _aspects(assessment):
    result=[]
    for code,label in ASPECT_LABELS.items():
        counts=assessment.get('aspects',{}).get(code,{})
        positive=counts.get('POSITIVE',0)
        total=positive+counts.get('NEUTRAL',0)+counts.get('NEGATIVE',0)
        if total>=3:
            result.append({'code':code,'label':label,'positive':positive,
                           'total':total,'percent':round(100*positive/total)})
    return result


def _evidence(assessment):
    reviews=[]
    available=[review for review in assessment.get('evidence',[]) if review.get('text','').strip()]
    available.sort(key=lambda review: (not bool(re.search(r'[à-ỹđÀ-ỸĐ]',review['text'])),
                                       abs(len(review['text'])-130)))
    for review in available:
        reviews.append({'id':review['id'],'text':review['text'][:240],
                        'rating':review.get('rating'),
                        'date':review.get('published_at') or review.get('date_text') or '',
                        'source_url':review_url(review.get('source_url'))})
        if len(reviews)==8: break
    return reviews


def build_assistant_view(store,analyzer,messages,profile,memory,feedback):
    """Map the latest assistant candidate set to display data without changing models."""
    latest=next((m for m in reversed(messages) if m['role']=='assistant'
                 and m['context'].get('candidate_ids')),None)
    if not latest: return {'restaurants':[],'query':'','location':profile.get('area',''),
                           'cuisine':'','error':False}
    context=latest['context']
    ids=context.get('candidate_ids',[])[:5]
    with store.connect() as db:
        rows=[dict(r) for r in db.execute(
            f"SELECT * FROM restaurants WHERE id IN ({','.join('?' for _ in ids)})",ids)] if ids else []
    for row in rows: row['assessment']=analyzer.assess(store,row['id'])
    recommended=context.get('recommended_restaurant_ids',[])
    if not recommended:
        latest_query=next((m['content'].strip().casefold() for m in reversed(messages)
                           if m['role']=='user'),'')
        previous=next((m for index,m in reversed(list(enumerate(messages[:-1])))
                       if m['role']=='assistant' and index>0
                       and messages[index-1]['role']=='user'
                       and messages[index-1]['content'].strip().casefold()==latest_query
                       and set(m['context'].get('candidate_ids',[]))==set(ids)
                       and m['context'].get('recommended_restaurant_ids')),None)
        if previous: recommended=previous['context']['recommended_restaurant_ids']
    ranked=rank_restaurants(rows,profile,memory,feedback,recommended,config='E')
    restaurants=[]
    for rank,row in enumerate(ranked,1):
        try: payload=json.loads(row['payload'])
        except (ValueError,TypeError): payload={}
        assessment=row['assessment']
        evidence=_evidence(assessment)
        restaurants.append({'id':row['id'],'rank':rank,'name':row['name'],
            'image':_image_url(payload),'rating':row['rating'],
            'reviewCount':row['total_reviews'],'address':row['address'] or '',
            'category':row['category'] or 'Nhà hàng','price':row['price'] or '',
            'sourceUrl':review_url(row['source_url']),
            'score':row['recommendation_score'],
            'scoreReason':row['recommendation_reason'],
            'feedbackSignal':row['feedback_signal'],
            'aspects':_aspects(assessment),'evidence':evidence,
            'reviewSnippet':evidence[0]['text'][:170] if evidence else '',
            'location':_coordinates(payload),
            'months':assessment.get('months',[])[-6:],
            'sampleCount':assessment.get('n',0),
            'model':assessment.get('model','rating-only')})
    query=next((m['content'] for m in reversed(messages) if m['role']=='user'),'')
    return {'restaurants':restaurants,'query':query,
            'location':context.get('location') or profile.get('area',''),
            'cuisine':context.get('extraction',{}).get('cuisine',''),
            'error':bool(context.get('error') or context.get('crawl_error'))}
