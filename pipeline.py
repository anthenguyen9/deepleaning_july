"""Reproducible ViTASA span-derived category/polarity baseline. Python 3.11."""
import argparse
import hashlib
import json
import random
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUT = ROOT / 'outputs'
COMMIT = 'cda6a4525bfdf7a7632a7d7c7ccdbe00af5b3094'
BASE = f'https://raw.githubusercontent.com/kh4nh12/ViTASA/{COMMIT}/'
ASPECTS = ['food', 'price', 'service', 'ambience', 'location']
POLARITIES = ['NEGATIVE', 'NEUTRAL', 'POSITIVE']
CLASSES = [f'{a}:{p}' for a in ASPECTS for p in POLARITIES]

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def normalize(text):
    return ' '.join(unicodedata.normalize('NFC', text).replace('\ufeff', '').split())

def mapped(tag):
    entity, attribute, polarity = tag.split('#')
    if polarity not in POLARITIES:
        raise ValueError(f'Unknown polarity: {tag}')
    aspect = 'price' if attribute == 'PRICE' else {
        'FOOD': 'food', 'DRINKS': 'food', 'SERVICE': 'service',
        'AMBIENCE': 'ambience', 'LOCATION': 'location'}.get(entity)
    return f'{aspect}:{polarity}' if aspect else None

def convert(row):
    text = row['data']
    labels = set()
    for start, end, tag in row['label']:
        if not 0 <= start < end <= len(text):
            raise ValueError(f'Invalid span in review {row["id"]}')
        label = mapped(tag)
        if label:
            labels.add(label)
    return {'id': str(row['id']), 'text': normalize(text), 'labels': sorted(labels)}

def download():
    DATA.mkdir(exist_ok=True)
    manifest = {'repository': 'https://github.com/kh4nh12/ViTASA', 'commit': COMMIT, 'files': {}}
    for name in ['restaurant.jsonl', 'LICENSE', 'README.md']:
        payload = urllib.request.urlopen(BASE + name, timeout=60).read()
        if name.endswith('jsonl'):
            rows = [json.loads(x) for x in payload.decode('utf-8').splitlines() if x.strip()]
            if not rows or not all({'id','data','label','labels'} <= r.keys() for r in rows):
                raise ValueError('Unexpected source schema')
        (DATA / name).write_bytes(payload)
        manifest['files'][name] = {'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
    dump(DATA / 'source_manifest.json', manifest)

def prepare():
    rows = [json.loads(x) for x in (DATA/'restaurant.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    groups = defaultdict(list)
    invalid = []
    for row in rows:
        try:
            item = convert(row)
            if not item['text']: raise ValueError('Empty text')
            groups[item['text'].casefold()].append(item)
        except (ValueError, KeyError, TypeError) as e:
            invalid.append({'id': row.get('id'), 'error': str(e)})
    # Conflicting exact duplicates are quarantined, not silently majority-voted.
    clean, conflicts = [], []
    for items in groups.values():
        if len({tuple(x['labels']) for x in items}) > 1:
            conflicts.extend(items)
        else:
            clean.append(items[0])
    clean.sort(key=lambda x: x['id'])
    random.Random(42).shuffle(clean)
    n = len(clean); a = int(n*.7); b = int(n*.8)
    splits = {'train':clean[:a], 'dev':clean[a:b], 'test':clean[b:]}
    for name, items in splits.items(): dump(DATA/f'{name}.json', items)
    dump(OUT/'audit.json', {'raw_rows':len(rows), 'clean_rows':n, 'invalid':invalid,
        'conflicting_duplicates':conflicts, 'exact_duplicates_removed':len(rows)-len(invalid)-len(conflicts)-n,
        'split_counts':{k:len(v) for k,v in splits.items()},
        'label_counts':{k:dict(Counter(t for r in v for t in r['labels'])) for k,v in splits.items()},
        'label_source':'label (span annotations); labels is preserved only in raw source, NOT merged',
        'limitations':['No timestamp or restaurant identity','Random exact-deduplicated split; not temporal or restaurant-disjoint',
            'Not equivalent to original ViTASA targeted-span benchmark','Near duplicates not removed']})
    print('Prepared:', {k:len(v) for k,v in splits.items()})

def targets(rows):
    import numpy as np
    return np.array([[int(c in r['labels']) for c in CLASSES] for r in rows])

def metrics(y, pred):
    from sklearn.metrics import classification_report, f1_score, accuracy_score
    return {'pair_micro_f1':f1_score(y,pred,average='micro',zero_division=0),
        'pair_macro_f1_15_labels':f1_score(y,pred,average='macro',zero_division=0),
        'exact_match':accuracy_score(y,pred),
        'per_label':classification_report(y,pred,target_names=CLASSES,output_dict=True,zero_division=0)}

def train():
    import joblib
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.svm import LinearSVC
    tr,dev,te = [read(DATA/f'{s}.json') for s in ['train','dev','test']]
    vectorizer = TfidfVectorizer(analyzer='char',ngram_range=(3,5),min_df=2,max_features=60000,sublinear_tf=True)
    x = vectorizer.fit_transform([r['text'] for r in tr])
    best, best_score, trials = None,-1,[]
    for c in [.1,1,3]:
        model = OneVsRestClassifier(LinearSVC(C=c,class_weight='balanced',random_state=42,max_iter=5000))
        model.fit(x,targets(tr))
        report = metrics(targets(dev),model.predict(vectorizer.transform([r['text'] for r in dev])))
        trials.append({'C':c,'dev_micro_f1':report['pair_micro_f1']})
        if report['pair_micro_f1'] > best_score:
            best,best_score = model,report['pair_micro_f1']
    OUT.mkdir(exist_ok=True)
    joblib.dump({'vectorizer':vectorizer,'model':best,'classes':CLASSES},OUT/'baseline.joblib')
    y = targets(te)
    pred = best.predict(vectorizer.transform([r['text'] for r in te]))
    majority = np.tile((targets(tr).mean(axis=0)>=.5).astype(int),(len(te),1))
    dump(OUT/'metrics.json',{'seed':42,'selection':'dev micro F1','trials':trials,'test':metrics(y,pred),
        'majority_test':metrics(y,majority)})
    dump(OUT/'test_predictions.json',[{'id':r['id'],'gold':r['labels'],'predicted':[c for c,v in zip(CLASSES,p) if v]} for r,p in zip(te,pred)])
    print('Test micro F1:',metrics(y,pred)['pair_micro_f1'])

def retrieve(query, k=5):
    """Lexical evidence search, NOT an LLM RAG system or restaurant recommender."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    rows = read(DATA/'train.json')
    v = TfidfVectorizer(analyzer='char',ngram_range=(3,5),max_features=60000)
    x = v.fit_transform([r['text'] for r in rows]); scores = (x @ v.transform([query]).T).toarray().ravel()
    return [dict(rows[i],score=float(scores[i])) for i in scores.argsort()[::-1][:k] if scores[i] > 0]

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command',choices=['download','prepare','train'])
    args = parser.parse_args()
    globals()[args.command]()
