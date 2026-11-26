"""CLI for recommendation A-E ablation evaluation."""
import argparse
import json
from recommendation_service import evaluate_file

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',required=True)
    parser.add_argument('--output',default='outputs/recommendation_metrics.json')
    parser.add_argument('--k',type=int,default=3)
    args=parser.parse_args()
    if args.k<1: parser.error('--k must be positive')
    print(json.dumps(evaluate_file(args.cases,args.output,args.k),ensure_ascii=False,indent=2))

if __name__=='__main__': main()
