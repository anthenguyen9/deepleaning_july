"""Explainable restaurant ranking and offline ablation evaluation."""
import json
import math
import re
from pathlib import Path

CONFIGS = ('A','B','C','D','E')

def _tokens(text):
    return {x for x in re.findall(r'\w+', (text or '').lower(), flags=re.UNICODE) if len(x) >= 3}

def _aspect_score(item, aspect):
    counts=item.get('assessment',{}).get('aspects',{}).get(aspect,{})
    pos=counts.get('POSITIVE',0); neg=counts.get('NEGATIVE',0); neutral=counts.get('NEUTRAL',0)
    total=pos+neg+neutral
    return ((pos-neg)/total) if total >= 3 else 0.0, total

def rank_restaurants(items, profile, memory, feedback_rows, recommended_ids=(), config='E'):
    """Rank candidates with cumulative A-E configurations for reproducible ablations."""
    if config not in CONFIGS: raise ValueError('Unknown recommendation configuration')
    feedback={x['restaurant_id']:x for x in feedback_rows}
    liked=' '.join((x.get('name','')+' '+x.get('category','')+' '+x.get('note',''))
                   for x in feedback_rows if x.get('signal')=='like')
    wanted=_tokens(' '.join([profile.get('cuisine',''),memory.get('explicit_notes',''),
                             memory.get('learned_summary',''),liked]))
    output=[]; recommended=set(recommended_ids)
    for raw in items:
        item=dict(raw); rating=item.get('rating') or 0; volume=item.get('total_reviews') or 0
        popularity=(rating/5)*0.75 + min(math.log1p(volume)/math.log1p(5000),1)*0.25
        aspect,mentions=_aspect_score(item,profile.get('aspect','food'))
        haystack=_tokens(' '.join([item.get('name',''),item.get('category',''),item.get('address','')]))
        overlap=len(wanted & haystack)/max(len(wanted),1)
        signal=feedback.get(item.get('id'),{}).get('signal')
        history=1.0 if signal=='like' else (-1.0 if signal=='dislike' else 0.0)
        evidence=min(item.get('assessment',{}).get('n_text',0)/10,1)
        chat=1.0 if item.get('id') in recommended else 0.0
        components={'popularity':round(popularity,4),'aspect':round(aspect,4),
                    'profile_match':round(overlap,4),'history':history,
                    'evidence':round(evidence,4),'chat':chat}
        score=popularity
        if config >= 'B': score += .35*aspect
        if config >= 'C': score += .30*overlap
        if config >= 'D': score += .45*history
        if config >= 'E': score += .10*evidence + .10*chat
        reasons=[f"Google {rating:.1f}/5"]
        if mentions>=3: reasons.append(f"{mentions} nhãn cho khía cạnh ưu tiên")
        if overlap>0: reasons.append('khớp hồ sơ khẩu vị')
        if signal: reasons.append('đã thích trước đây' if signal=='like' else 'đã đánh dấu không hợp')
        item.update(recommendation_score=round(score,4),score_components=components,
                    recommendation_reason='; '.join(reasons),feedback_signal=signal,
                    preference_score=round(max(0,(aspect+1)/2)*100) if mentions>=3 else None)
        output.append(item)
    return sorted(output,key=lambda x:(x['recommendation_score'],x.get('rating') or 0,
                                       x.get('total_reviews') or 0),reverse=True)

def evaluate_cases(cases, k=3):
    """Evaluate configurations A-E over labeled candidate lists."""
    report={'k':k,'queries':len(cases),'configurations':{}}
    for config in CONFIGS:
        recalls=[]; reciprocal=[]; ndcgs=[]
        for case in cases:
            ranked=rank_restaurants(case['candidates'],case.get('profile',{}),case.get('memory',{}),
                                    case.get('feedback',[]),case.get('recommended_ids',[]),config)
            ids=[x['id'] for x in ranked[:k]]; relevant=set(case.get('relevant_restaurant_ids',[]))
            if not relevant: continue
            hits=sum(x in relevant for x in ids); recalls.append(hits/len(relevant))
            positions=[i+1 for i,x in enumerate(ids) if x in relevant]
            reciprocal.append(1/min(positions) if positions else 0)
            dcg=sum(1/math.log2(i+2) for i,x in enumerate(ids) if x in relevant)
            ideal=sum(1/math.log2(i+2) for i in range(min(len(relevant),k)))
            ndcgs.append(dcg/ideal if ideal else 0)
        n=len(recalls)
        report['configurations'][config]={'judged_queries':n,
            'recall_at_k':round(sum(recalls)/n,4) if n else None,
            'mrr':round(sum(reciprocal)/n,4) if n else None,
            'ndcg_at_k':round(sum(ndcgs)/n,4) if n else None}
    return report

def evaluate_file(input_path, output_path, k=3):
    cases=json.loads(Path(input_path).read_text(encoding='utf-8'))
    report=evaluate_cases(cases,k)
    Path(output_path).parent.mkdir(parents=True,exist_ok=True)
    Path(output_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
