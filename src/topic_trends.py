"""Optional BERTopic retrospective topic-frequency experiment.

Requires source-dated reviews. This is not BERTrend online learning or forecasting.
"""
import argparse
import json
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from data_pipeline import DEFAULT_DB, ROOT
from dense_service import MODEL,encode
from pipeline import dump
from storage import Store


def run(store,output,min_months=6,min_reviews_per_month=30,min_topic_size=15):
    with store.connect() as db:
        rows=[dict(r) for r in db.execute("SELECT restaurant_id,id,text,published_at FROM reviews WHERE published_at IS NOT NULL AND trim(text)<>'' ORDER BY published_at,restaurant_id,id")]
    months=Counter(r['published_at'][:7] for r in rows)
    eligible={m for m,n in months.items() if n>=min_reviews_per_month}
    coverage={'dated_text_reviews':len(rows),'months':dict(sorted(months.items())),
              'minimum_months':min_months,'minimum_reviews_per_month':min_reviews_per_month}
    if len(eligible)<min_months:
        report={'method':'BERTopic topics_over_time','status':'not_run',
                'reason':'insufficient_temporal_coverage','coverage':coverage}
        dump(Path(output),report);return report
    from bertopic import BERTopic
    selected=[r for r in rows if r['published_at'][:7] in eligible]
    texts=[r['text'] for r in selected]
    embedding_model=os.getenv('EMBEDDING_MODEL',MODEL)
    embeddings=encode(texts,embedding_model,query=False)
    model=BERTopic(language='multilingual',min_topic_size=min_topic_size,
                   calculate_probabilities=False,embedding_model=None)
    topics,_=model.fit_transform(texts,embeddings=embeddings)
    dates=[r['published_at'][:7]+'-01' for r in selected]
    trajectory=model.topics_over_time(texts,dates,topics=topics,global_tuning=True)
    report={'method':'BERTopic topics_over_time','status':'completed','coverage':coverage,
            'embedding_model':embedding_model,'topic_count':len(set(topics)-{-1}),
            'outliers':topics.count(-1),
            'topic_month_rows':json.loads(trajectory.to_json(orient='records',date_format='iso')),
            'claim':'Retrospective topic frequency; no BERTrend or forecast claim.'}
    dump(Path(output),report);return report


if __name__=='__main__':
    load_dotenv(ROOT/'.env')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=str(DEFAULT_DB))
    parser.add_argument('--output',default='outputs/topic_trends.json')
    parser.add_argument('--min-months',type=int,default=6)
    parser.add_argument('--min-reviews-per-month',type=int,default=30)
    parser.add_argument('--min-topic-size',type=int,default=15)
    args=parser.parse_args()
    print(json.dumps(run(Store(args.db),args.output,args.min_months,args.min_reviews_per_month,
                         args.min_topic_size),ensure_ascii=False,indent=2))
