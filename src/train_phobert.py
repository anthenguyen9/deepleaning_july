"""Optional multi-label PhoBERT reference experiment; not yet validated on Windows/GPU."""
import argparse
import random
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from underthesea import word_tokenize
from pipeline import DATA, OUT, CLASSES, read, targets, metrics, dump

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--epochs',type=int,default=3)
    p.add_argument('--batch-size',type=int,default=4)
    args=p.parse_args()
    if args.epochs < 1 or args.batch_size < 1: p.error('Arguments must be positive')
    random.seed(42);np.random.seed(42);torch.manual_seed(42)
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    name='vinai/phobert-base-v2'
    tokenizer=AutoTokenizer.from_pretrained(name,use_fast=False)
    model=AutoModelForSequenceClassification.from_pretrained(name,num_labels=len(CLASSES),
        problem_type='multi_label_classification',id2label=dict(enumerate(CLASSES)),
        label2id={c:i for i,c in enumerate(CLASSES)}).to(device)
    splits={s:read(DATA/f'{s}.json') for s in ['train','dev','test']}
    texts={s:[word_tokenize(r['text'],format='text') for r in rows] for s,rows in splits.items()}
    ys={s:torch.tensor(targets(rows),dtype=torch.float32) for s,rows in splits.items()}
    optimizer=torch.optim.AdamW(model.parameters(),lr=2e-5,weight_decay=.01)
    def batch(s,indices):
        return tokenizer([texts[s][i] for i in indices],padding=True,truncation=True,
            max_length=256,return_tensors='pt').to(device)
    def evaluate(s):
        model.eval();pred=[]
        with torch.no_grad():
            for start in range(0,len(texts[s]),args.batch_size):
                ids=list(range(start,min(start+args.batch_size,len(texts[s]))))
                pred.extend((model(**batch(s,ids)).logits.sigmoid()>=.5).cpu().numpy())
        return metrics(ys[s].numpy(),np.array(pred))
    best=-1;history=[];destination=OUT/'phobert'
    for epoch in range(args.epochs):
        model.train();order=torch.randperm(len(texts['train'])).tolist()
        for start in range(0,len(order),args.batch_size):
            ids=order[start:start+args.batch_size];optimizer.zero_grad()
            loss=model(**batch('train',ids),labels=ys['train'][ids].to(device)).loss
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        report=evaluate('dev');history.append({'epoch':epoch+1,'dev':report})
        print(epoch+1,report['pair_micro_f1'])
        if report['pair_micro_f1']>best:
            best=report['pair_micro_f1'];model.save_pretrained(destination);tokenizer.save_pretrained(destination)
    model=AutoModelForSequenceClassification.from_pretrained(destination).to(device)
    dump(OUT/'phobert_metrics.json',{'history':history,'test':evaluate('test'),
        'seed':42,'threshold':.5,'segmentation':'underthesea (not original VnCoreNLP)',
        'architecture':'single-head 15-label reference; NOT proposed ACD+SPC multi-task architecture',
        'truncation':'first 256 tokens; long review labels may be outside retained context'})

if __name__=='__main__':main()
