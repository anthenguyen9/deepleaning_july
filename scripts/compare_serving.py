"""Single-review CPU latency on a fixed test prefix, including text preprocessing."""
import argparse
import gc
import time
from pathlib import Path

import joblib
import numpy as np
import torch
from transformers import AutoTokenizer
from underthesea import word_tokenize

from pipeline import dump, read
from train_phobert_multitask import ABSA


def run(model_dir, output):
    torch.set_num_threads(4)
    rows = read(Path('data/test.json'))[:50]
    baseline = joblib.load('outputs/baseline.joblib')
    checkpoint = torch.load(model_dir / 'model.pt', map_location='cpu', weights_only=True)
    model = ABSA(checkpoint['backbone'])
    model.load_state_dict(checkpoint['weights'])
    acd_threshold, spc_threshold = checkpoint['acd_threshold'], checkpoint['spc_threshold']
    del checkpoint
    gc.collect()
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(model_dir / 'tokenizer', use_fast=False)
    config = read(model_dir / 'metrics.json')['config']

    def svm(text):
        return baseline['model'].predict(baseline['vectorizer'].transform([text]))

    def phobert(text):
        segmented = word_tokenize(text, format='text')
        inputs = tokenizer(segmented, return_tensors='pt', truncation=True, max_length=config['max_length'])
        with torch.inference_mode():
            a, p = model(**inputs)
            return ((p.sigmoid() >= spc_threshold) & (a.sigmoid() >= acd_threshold).unsqueeze(-1)).reshape(-1, 15)

    report = {'device': 'cpu', 'torch_threads': 4, 'reviews': len(rows),
              'protocol': 'First 50 locked test reviews; batch one; three warmups; preprocessing included; startup excluded',
              'limitations': 'Single local run, not concurrent-load SLA or deployment speed guarantee', 'methods': {}}
    for name, fn in [('svm', svm), ('phobert', phobert)]:
        for row in rows[:3]:
            fn(row['text'])
        times = []
        for row in rows:
            start = time.perf_counter()
            fn(row['text'])
            times.append((time.perf_counter() - start) * 1000)
        report['methods'][name] = {'median_ms': float(np.median(times)), 'p95_ms': float(np.percentile(times, 95))}
    dump(output, report)
    print(report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('outputs/serving_latency.json'))
    args = parser.parse_args()
    run(args.model_dir, args.output)
