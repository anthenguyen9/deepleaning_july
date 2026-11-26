"""Reproducible uncertainty/leakage audit; no model fitting or split changes."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from pipeline import CLASSES, dump, read


def audit(data, predictions, output, repetitions=2000):
    splits={s:read(data/f'{s}.json') for s in ('train','dev','test')}
    rows=read(predictions)
    lookup={str(r['id']):r for r in rows}
    assert len(lookup)==len(rows)==len(splits['test']), 'Prediction IDs mismatch'
    ordered=[lookup[str(r['id'])] for r in splits['test']]
    assert all(set(p['gold'])==set(r['labels']) for p,r in zip(ordered,splits['test']))
    y=np.array([[c in r['gold'] for c in CLASSES] for r in ordered],dtype=int)
    p=np.array([[c in r['predicted'] for c in CLASSES] for r in ordered],dtype=int)
    tp=y*p;fp=(1-y)*p;fn=y*(1-p)
    rng=np.random.default_rng(42);scores=[]
    for _ in range(repetitions):
        ix=rng.integers(0,len(y),len(y));t=tp[ix].sum(0);f=fp[ix].sum(0);n=fn[ix].sum(0)
        den=2*t+f+n
        scores.append([float(2*t.sum()/max(1,den.sum())),
                       float(np.divide(2*t,den,out=np.zeros(15),where=den!=0).mean())])
    texts=[r['text'] for s in splits.values() for r in s]
    vectorizer=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),min_df=1)
    matrix=vectorizer.fit_transform(texts)
    offsets={};start=0
    for s,rs in splits.items():offsets[s]=(start,start+len(rs));start+=len(rs)
    duplicates=[]
    for a,b in [('train','dev'),('train','test'),('dev','test')]:
        a0,a1=offsets[a];b0,b1=offsets[b]
        sim=(matrix[a0:a1]@matrix[b0:b1].T).tocoo()
        for i,j,score in zip(sim.row,sim.col,sim.data):
            if score>=.90:
                duplicates.append({'split_a':a,'id_a':splits[a][i]['id'],
                                   'split_b':b,'id_b':splits[b][j]['id'],'cosine':float(score)})
    report={'seed':42,'bootstrap_repetitions':repetitions,'sampling_unit':'review',
            'confidence_level':.95,'ci_percentile':dict(zip(['pair_micro_f1','pair_macro_f1_15_labels'],
             np.quantile(np.asarray(scores),[.025,.975],axis=0).T.tolist())),
            'dataset_sha256':{s:hashlib.sha256((data/f'{s}.json').read_bytes()).hexdigest() for s in splits},
            'prediction_sha256':hashlib.sha256(predictions.read_bytes()).hexdigest(),
            'support':dict(zip(CLASSES,y.sum(0).tolist())),
            'near_duplicate_method':'char_wb TF-IDF 3-5 cosine >= 0.90; audit only, no fitting or split modification',
            'near_duplicate_pairs':sorted(duplicates,key=lambda x:-x['cosine']),
            'limitations':['Not a restaurant-cluster CI: ViTASA conversion has no restaurant identifiers.',
              'Historical test split has already been reported; this is uncertainty analysis, not a fresh independent experiment.',
              'Near-duplicate matches are review candidates, not automatic grounds to remove test rows.']}
    dump(output,report)
    print(json.dumps({'confidence_intervals':report['ci_percentile'],'near_duplicate_pairs':len(duplicates)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=Path('data'))
    p.add_argument('--predictions',type=Path,default=Path('outputs/test_predictions.json'))
    p.add_argument('--output',type=Path,default=Path('outputs/baseline_uncertainty.json'))
    a=p.parse_args();audit(a.data,a.predictions,a.output)
