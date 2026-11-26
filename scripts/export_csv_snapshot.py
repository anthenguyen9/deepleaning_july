"""Export a public CSV snapshot without changing either live FoodLens database.

Run from the repository root: python -m scripts.export_csv_snapshot --output datasets/csv/2026-11-26
Only the explicit publication fields below are exported. Account data and raw
provider/cache payloads stay private. Existing output directories are never replaced.
"""
import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
import struct
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
ASPECTS=('food','price','service','ambience','location')
POLARITIES=('NEGATIVE','NEUTRAL','POSITIVE')
LABELS=tuple(f'{a}:{p}' for a in ASPECTS for p in POLARITIES)
PUBLIC_TABLES={
    'locations': 'id code name normalized_name parent_id level is_active effective_from effective_to source source_id imported_at',
    'location_aliases': 'location_id alias normalized_alias',
    'restaurant_locations': 'restaurant_id location_id',
    'review_languages': 'restaurant_id review_id policy_version text_hash decision top_language top_confidence vi_confidence classified_at',
    'monthly_trends': 'restaurant_id month aspect review_count positive_count neutral_count negative_count average_rating model_version updated_at',
    'period_aggregates': 'restaurant_id granularity period aspect review_count positive_count neutral_count negative_count average_rating model_version updated_at',
    'trend_signals': 'restaurant_id month aspect review_count volume_change average_rating rating_change moving_average_rating sentiment_index sentiment_shift trend_score signal_level sufficient_sample model_version updated_at',
    'ingestion_seeds': 'id area cuisine enabled last_run_at',
    'restaurant_crawl_state': 'restaurant_id pages_fetched review_requests status last_attempt_at last_success_at',
    'dataset_versions': 'id version created_at restaurant_count review_count dated_review_count min_review_date max_review_date source',
    'api_calls': 'id engine created_at status',
    'crawl_runs': 'id location_id query query_hash year_month provider status started_at completed_at result_count',
    'pipeline_jobs': 'id job_type status started_at finished_at',
    'review_documents': 'document_key restaurant_id review_id text restaurant_name category updated_at',
    'evaluation_queries': 'id query split',
}
PRIVATE_REASONS={
    'accounts':'Account identities, password hashes and preference profiles',
    'profile':'Personal profile', 'preference_memory':'Personal preference memory',
    'assistant_messages':'Private conversations', 'chat_messages':'Private conversations',
    'chat_sessions':'Private conversation sessions', 'user_feedback':'Private user feedback',
    'restaurant_feedback':'Private feedback notes', 'user_searches':'Account-search associations',
    'searches':'Personal search history and duplicate nested results',
    'retrieval_events':'Personal queries and diagnostic traces',
    'api_cache':'Raw provider payloads and duplicate cached data',
}
RESTAURANT_ATTRIBUTES={'data_id','place_id','data_cid','provider_id','gps_coordinates',
    'website','phone','open_state','hours','operating_hours','type','types','type_id',
    'type_ids','price','extracted_price','extensions','service_options','country',
    'serpapi_thumbnail'}
TEXT_FIELDS={'text','data','query','note','notes','task_prompt','result_summary','comment','boundary_note'}
EMAIL=re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b')
PHONE=re.compile(r'(?<!\w)(?:\+84[ .-]?|0)(?:\d[ .-]?){8,10}\d(?!\w)')


def leaves(value,path=''):
    """Lossless JSON structure in CSV path/type/value rows, including empty values."""
    if isinstance(value,dict) and value:
        for key,child in value.items():
            yield from leaves(child,f'{path}.{key}' if path else key)
    elif isinstance(value,list) and value:
        for index,child in enumerate(value): yield from leaves(child,f'{path}[{index}]')
    else:
        kind=('null' if value is None else 'empty_object' if value=={} else
              'empty_array' if value==[] else type(value).__name__)
        yield {'field_path':path,'value_type':kind,'value':None if isinstance(value,(dict,list)) else value}


def parse(value):
    return json.loads(value) if isinstance(value,str) else value


def label_fields(labels):
    if labels is not None and (not isinstance(labels,list) or set(labels)-set(LABELS)):
        raise ValueError('Unexpected ABSA label format; refusing to discard labels.')
    fields={f'{a}_{p.lower()}':int(f'{a}:{p}' in labels) if labels is not None else None
            for a in ASPECTS for p in POLARITIES}
    return {'labels':'|'.join(labels) if labels is not None else None,
            'labels_available':int(labels is not None),**fields}


class Export:
    def __init__(self,output):
        self.output=output.resolve()
        if self.output.exists(): raise FileExistsError(self.output)
        self.output.mkdir(parents=True)
        self.timestamp=datetime.now(timezone.utc).isoformat()
        self.manifest=[];self.inventory=[];self.sources=[];self.validation=[]
        self.secrets=[]
        for path in (ROOT/'.env',ROOT/'instance/docker_demo.env'):
            for name,value in dotenv_values(path).items():
                if value and len(value)>=8 and re.search(r'KEY|SECRET|TOKEN|PASSWORD',name,re.I):
                    self.secrets.append(value)

    def cell(self,value,field=''):
        if value is None: return ''
        if isinstance(value,bool): return int(value)
        if isinstance(value,(dict,list,bytes)): raise TypeError(f'Unflattened field: {field}')
        if isinstance(value,str):
            for secret in self.secrets: value=value.replace(secret,'[REDACTED_SECRET]')
            if field in TEXT_FIELDS or field=='value':
                value=EMAIL.sub('[REDACTED_EMAIL]',value)
                value=PHONE.sub('[REDACTED_PHONE]',value)
            # CSV cells are data, never formulas when opened in Excel.
            if value.lstrip().startswith(('=','+','-','@')): value="'"+value
            return value
        if isinstance(value,float) and not math.isfinite(value):
            raise ValueError('Non-finite number in source data.')
        return value

    def write(self,name,columns,rows,source='',expected=None):
        path=self.output/name
        path.parent.mkdir(parents=True,exist_ok=True)
        count=0
        with path.open('w',encoding='utf-8-sig',newline='') as handle:
            writer=csv.writer(handle)
            writer.writerow(columns)
            for row in rows:
                writer.writerow([self.cell(row.get(col),col) for col in columns]);count+=1
        with path.open(encoding='utf-8-sig',newline='') as handle:
            reader=csv.reader(handle)
            assert next(reader)==columns
            actual=0
            for row in reader:
                if len(row)!=len(columns): raise ValueError(f'Invalid CSV width: {name}')
                actual+=1
        if actual!=count or (expected is not None and count!=expected):
            raise ValueError(f'Row count mismatch: {name}, {actual}/{expected}')
        content=path.read_bytes()
        if any(secret.encode('utf-8') in content for secret in self.secrets):
            raise ValueError(f'Secret detected: {name}')
        if len(content)>40*1024*1024: raise ValueError(f'CSV too large for regular Git: {name}')
        self.manifest.append({'file':name,'rows':count,'columns':len(columns),'bytes':len(content),
            'sha256':hashlib.sha256(content).hexdigest(),'source':source,'exported_at':self.timestamp})
        self.validation.append({'check':'csv_roundtrip_and_source_count','file':name,
                                'expected_rows':expected if expected is not None else count,
                                'actual_rows':actual,'result':'pass'})
        return count

    def records(self,name,records,source='',expected=None):
        rows=list(records)
        columns=list(dict.fromkeys(key for row in rows for key in row))
        return self.write(name,columns or ['record_index'],rows,source,expected)

    def database(self,source_name,folder):
        source=ROOT/'instance'/f'{source_name}.sqlite3'
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original, \
                closing(sqlite3.connect(':memory:')) as db:
            original.backup(db)
            db.row_factory=sqlite3.Row
            if db.execute('pragma integrity_check').fetchone()[0]!='ok': raise ValueError('Invalid source database')
            self.sources.append({'source':f'instance/{source.name}','snapshot':folder,
                'sha256':hashlib.sha256(db.serialize()).hexdigest(),'method':'SQLite online backup to memory',
                'exported_at':self.timestamp})
            tables={row[0]:row[1] for row in db.execute("select name,sql from sqlite_master where type='table'")}
            for table in sorted(tables):
                count=db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                action='exported'
                reason='Explicit public fields; raw payloads and tokens omitted'
                if table.startswith(('sqlite_','review_fts')):
                    action='excluded';reason='Rebuildable SQLite/FTS internals'
                elif table in PRIVATE_REASONS:
                    action='excluded';reason=PRIVATE_REASONS[table]
                elif table in PUBLIC_TABLES:
                    columns=PUBLIC_TABLES[table].split()
                    query='SELECT '+','.join(f'"{c}"' for c in columns)+f' FROM "{table}" ORDER BY '+','.join(f'"{c}"' for c in columns[:2])
                    self.write(f'{folder}/{table}.csv',columns,(dict(row) for row in db.execute(query)),table,count)
                elif table=='restaurants': self.restaurants(db,folder,count)
                elif table=='reviews': self.reviews(db,folder,count)
                elif table in {'analyses','gold_annotations'}: self.annotations(db,folder,table,count)
                elif table=='dense_vectors': self.vectors(db,folder,count)
                elif table=='study_evaluations':
                    reason='Anonymous participant IDs and numeric ratings; free text and submission timestamps omitted'
                    people={row[0]:f'P{index:03d}' for index,row in enumerate(db.execute(
                        'SELECT DISTINCT participant_code FROM study_evaluations ORDER BY participant_code'),1)}
                    columns=['participant_id','sample_no','consent','usefulness','ease_of_use','trust',
                             'relevance','reuse_intent','duration_seconds','task_success']
                    rows=({**dict(row),'participant_id':people[row['participant_code']]} for row in db.execute(
                        'SELECT * FROM study_evaluations ORDER BY participant_code,sample_no'))
                    self.write(f'{folder}/{table}.csv',columns,rows,table,count)
                else:
                    raise ValueError(f'Unclassified table: {table}; review before publishing.')
                self.inventory.append({'snapshot':folder,'table':table,'source_rows':count,'action':action,'reason':reason})

    def restaurants(self,db,folder,count):
        rows=[];attributes=[]
        for original in db.execute('SELECT * FROM restaurants ORDER BY id'):
            row=dict(original);payload=parse(row.pop('payload'))
            gps=payload.get('gps_coordinates') or {}
            row.update(latitude=gps.get('latitude'),longitude=gps.get('longitude'),
                       place_id=payload.get('place_id'),provider_id=payload.get('provider_id'))
            rows.append(row)
            for key,value in payload.items():
                if key in RESTAURANT_ATTRIBUTES:
                    attributes.extend({'restaurant_id':row['id'],**leaf} for leaf in leaves(value,key))
        self.records(f'{folder}/restaurants.csv',rows,'restaurants',count)
        self.records(f'{folder}/restaurant_attributes.csv',attributes,'restaurants.payload public fields')

    def reviews(self,db,folder,count):
        columns=['restaurant_id','id','text','rating','published_at','date_text','raw_iso_date',
                 'raw_iso_date_of_last_edit','source_url','fetched_at','text_redacted']
        def rows():
            for original in db.execute('SELECT * FROM reviews ORDER BY restaurant_id,id'):
                row=dict(original);payload=parse(row.pop('payload'))
                # Preserve raw precision. Never infer a specific day from month/year text.
                row.update(raw_iso_date=payload.get('iso_date'),
                    raw_iso_date_of_last_edit=payload.get('iso_date_of_last_edit'),
                    text_redacted=int(EMAIL.search(row['text']) is not None or PHONE.search(row['text']) is not None))
                yield row
        self.write(f'{folder}/reviews.csv',columns,rows(),'reviews',count)

    def annotations(self,db,folder,table,count):
        rows=[]
        for original in db.execute(f'SELECT * FROM {table} ORDER BY restaurant_id,review_id'):
            row=dict(original)
            labels=parse(row.pop('labels_json' if table=='gold_annotations' else 'labels'))
            row.update(label_fields(labels))
            if table=='gold_annotations':
                row['annotation_origin']='ai' if row['annotator'].startswith('ai:') else 'account_annotation_unverified'
            rows.append(row)
        columns=list(rows[0]) if rows else ['restaurant_id','review_id','text_hash',*label_fields([])]
        self.write(f'{folder}/{table}.csv',columns,rows,table,count)

    def vectors(self,db,folder,count):
        total=0;part=1;batch=[];columns=None
        for original in db.execute('SELECT * FROM dense_vectors ORDER BY model,dimension,document_key'):
            row=dict(original);raw=row.pop('vector');dimension=row['dimension']
            if len(raw)!=dimension*4: raise ValueError('Unexpected vector encoding')
            values=struct.unpack(f'<{dimension}f',raw)
            row.update({f'v{i:04d}':float(format(value,'.9g')) for i,value in enumerate(values)})
            if columns is not None and (len(batch)>=1000 or list(row)!=columns):
                self.write(f'{folder}/dense_vectors/part_{part:03d}.csv',columns,batch,'dense_vectors',len(batch))
                total+=len(batch);part+=1;batch=[]
            columns=list(row);batch.append(row)
        if batch:
            self.write(f'{folder}/dense_vectors/part_{part:03d}.csv',columns,batch,'dense_vectors',len(batch));total+=len(batch)
        if total!=count: raise ValueError('Vector count mismatch')

    def source_file(self,path,folder):
        relative=path.relative_to(ROOT).as_posix();raw=path.read_bytes()
        self.sources.append({'source':relative,'snapshot':folder,'sha256':hashlib.sha256(raw).hexdigest(),
                             'method':'Read-only file conversion','exported_at':self.timestamp})
        data=([json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
              if path.suffix=='.jsonl' else json.loads(raw.decode('utf-8-sig')))
        records=data.get('records') if isinstance(data,dict) else data
        if isinstance(records,list) and records and all(isinstance(row,dict) for row in records):
            if all('text' in row and isinstance(row.get('labels'),(list,type(None))) for row in records):
                rows=[]
                for index,original in enumerate(records):
                    row={k:v for k,v in original.items() if k!='labels'}
                    if any(isinstance(v,(dict,list)) for v in row.values()): break
                    row={'record_index':index,**row,**label_fields(original.get('labels'))}
                    rows.append(row)
                else:
                    self.records(f'{folder}.csv',rows,relative,len(records))
                    if isinstance(data,dict):
                        self.records(f'{folder}_metadata.csv',leaves({k:v for k,v in data.items() if k!='records'}),relative)
                    return
            # Nested evaluation candidates / original spans are represented without JSON cells.
            self.records(f'{folder}.csv',({'record_index':index,**leaf} for index,row in enumerate(records)
                                         for leaf in leaves(row)),relative)
            if isinstance(data,dict):
                self.records(f'{folder}_metadata.csv',leaves({k:v for k,v in data.items() if k!='records'}),relative)
        else:
            self.records(f'{folder}.csv',leaves(data),relative)

    def finish(self):
        self.records('source_inventory.csv',self.inventory,'source database inventory')
        self.records('sources.csv',self.sources,'input checksums')
        self.records('validation.csv',list(self.validation),'CSV/source reconciliation')
        self.records('manifest.csv',list(self.manifest),'export file checksums (manifest excludes itself)')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    export=Export(args.output)
    export.database('demo_tunnel','operational')
    export.database('food_reviews','research')
    for path in sorted((ROOT/'data').rglob('*')):
        if path.suffix not in {'.json','.jsonl'}: continue
        relative=path.relative_to(ROOT/'data').with_suffix('').as_posix()
        export.source_file(path,'training/'+relative)
    for path in sorted((ROOT/'location_data').glob('*.json')):
        export.source_file(path,'geography/'+path.stem)
    # Preserve the upstream license; it does not relicense Google Maps review data.
    (export.output/'VITASA_LICENSE.txt').write_bytes((ROOT/'data/LICENSE').read_bytes())
    export.finish()
    print(json.dumps({'output':str(export.output),'csv_files':len(export.manifest),
                      'total_bytes':sum(row['bytes'] for row in export.manifest),
                      'exported_at':export.timestamp}))


if __name__=='__main__': main()
