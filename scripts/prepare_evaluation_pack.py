"""Prepare blinded annotation workbooks from real reviews; never invent judgments."""
import argparse
import collections
import hashlib
import random
from pathlib import Path

from pipeline import dump, normalize
from storage import Store

QUERIES=[
 'Quán hải sản có view biển ở Đà Nẵng', 'Quán hải sản ở Hòa Xuân',
 'Quán thịt nướng gần Hải Châu', 'Quán ăn gia đình ở Sơn Trà',
 'Quán giá hợp lý ở Ngũ Hành Sơn', 'Nhà hàng yên tĩnh để trò chuyện',
 'Nhà hàng phục vụ nhanh, nhân viên thân thiện', 'Quán có món chay',
 'Quán có chỗ đỗ xe thuận tiện', 'Quán sạch sẽ phù hợp trẻ em',
 'Review phàn nàn giá cao', 'Review về món ăn nguội hoặc phục vụ chậm',
 'Quán hải sản tươi ở Thanh Khê', 'Quán ăn sáng gần biển',
 'Seafood restaurant with a sea view in Da Nang', 'Affordable dinner in Hai Chau',
 'Friendly service and vegetarian options', 'Quiet restaurant suitable for a family',
 'Nhà hàng nổi bật tại Liên Chiểu', 'Quán ăn ở Cẩm Lệ có giá hợp lý']


def prepare(db, output):
    if output.exists(): raise ValueError('Evaluation pack exists; preserve annotator work')
    store=Store(db);rng=random.Random(42);groups=collections.defaultdict(list);seen=set()
    with store.connect() as conn:
        records=[dict(r) for r in conn.execute("SELECT restaurant_id,id,text,published_at FROM reviews WHERE length(trim(text))>=20 ORDER BY restaurant_id,id")]
    for r in records:
        key=normalize(r['text']).casefold()
        if key not in seen:groups[r['restaurant_id']].append(r);seen.add(key)
    restaurants=sorted(k for k,v in groups.items() if len(v)>=8);rng.shuffle(restaurants)
    selected=restaurants[:30];rows=[]
    for i,rid in enumerate(selected):
        candidates=groups[rid];rng.shuffle(candidates)
        for r in candidates[:10]:
            rows.append({'restaurant_id':rid,'review_id':r['id'],'text':r['text'],
                         'published_at':r['published_at'],'labels':None,'annotator':'',
                         'reviewed':False,'annotation_origin':'pending_independent_human',
                         'planned_split':'dev' if i<10 else 'test'})
    for reviewer in ['A','B']:
        shuffled=rows.copy();rng.shuffle(shuffled)
        dump(output/f'annotator_{reviewer}.json',{'status':'unlabelled','records':shuffled})
    dump(output/'retrieval_queries.json',[{'id':f'Q{i:02d}','query':q,
          'split':'dev' if i<=6 else 'test','judgments':None,'reviewed':False} for i,q in enumerate(QUERIES,1)])
    manifest={'seed':42,'restaurants':len(selected),'reviews':len(rows),'status':'awaiting_two_independent_annotators',
              'restaurant_splits':{'dev':selected[:10],'test':selected[10:]},
              'sampling':'30 eligible restaurants shuffled, up to 10 deduplicated reviews each; not population-representative',
              'blinding':'Star rating, model predictions and existing automatic labels withheld from both reviewer forms',
              'source_digest':hashlib.sha256(str([(r['restaurant_id'],r['review_id'],r['text']) for r in rows]).encode()).hexdigest(),
              'caution':'Do not train on these reserved restaurants or mark reviewed before actual human review.'}
    dump(output/'manifest.json',manifest)
    print({'restaurants':len(selected),'review_forms':len(rows),'queries':len(QUERIES),'output':str(output)})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',default='instance/food_reviews.sqlite3')
    p.add_argument('--output',type=Path,default=Path('data/evaluation_20260919'))
    a=p.parse_args();prepare(a.db,a.output)
