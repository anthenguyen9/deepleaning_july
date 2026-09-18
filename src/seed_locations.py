"""Idempotent location seed from checked-in government and OSM snapshots."""
import argparse

from data_pipeline import DEFAULT_DB
from locations import seed_danang
from storage import Store

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--city',default='Da Nang',choices=['Da Nang','Đà Nẵng'])
    parser.add_argument('--db',default=str(DEFAULT_DB))
    args=parser.parse_args()
    print(seed_danang(Store(args.db)))
