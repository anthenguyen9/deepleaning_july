"""PhoBERT two-head ACD and SPC on locked restaurant-review splits."""
import argparse
import json
import random
import hashlib
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader,Dataset
from transformers import AutoModel,AutoTokenizer
from underthesea import word_tokenize

from pipeline import CLASSES,dump,metrics,read


def targets(rows):
    pair=np.array([[int(c in r['labels']) for c in CLASSES] for r in rows],dtype=np.float32).reshape(-1,5,3)
    return (pair.sum(axis=2)>0).astype(np.float32),pair


class Reviews(Dataset):
    def __init__(self,rows,tokenizer,max_length):
        text=[word_tokenize(r['text'],format='text') for r in rows]
        self.tokens=tokenizer(text,truncation=True,max_length=max_length)
        self.acd,self.spc=targets(rows)
    def __len__(self): return len(self.acd)
    def __getitem__(self,i):
        return {**{k:v[i] for k,v in self.tokens.items()},'acd':self.acd[i],'spc':self.spc[i]}


class ABSA(nn.Module):
    def __init__(self,backbone):
        super().__init__();self.encoder=AutoModel.from_pretrained(backbone)
        size=self.encoder.config.hidden_size
        self.drop=nn.Dropout(.1);self.acd=nn.Linear(size,5);self.spc=nn.Linear(size,15)
    def forward(self,**inputs):
        state=self.drop(self.encoder(**inputs).last_hidden_state[:,0])
        return self.acd(state),self.spc(state).reshape(-1,5,3)


def train(args):
    if args.epochs<1 or args.batch_size<1: raise ValueError('epochs and batch size must be positive')
    if args.threads<1 or args.accumulation<1: raise ValueError('threads and accumulation must be positive')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    if (args.output_dir/'metrics.json').exists(): raise ValueError('Use a new output directory; existing experiment is protected')
    torch.set_num_threads(args.threads)
    started=time.perf_counter()
    random.seed(args.seed);np.random.seed(args.seed);torch.manual_seed(args.seed)
    rows={s:read(args.data_dir/f'{s}.json') for s in ('train','dev','test')}
    if any(not v for v in rows.values()): raise ValueError('All locked splits must be nonempty')
    hashes={s:hashlib.sha256((args.data_dir/f'{s}.json').read_bytes()).hexdigest() for s in rows}
    texts={s:{' '.join(r['text'].split()).casefold() for r in rs} for s,rs in rows.items()}
    if any(texts[a]&texts[b] for a,b in [('train','dev'),('train','test'),('dev','test')]):
        raise ValueError('Exact normalized duplicate text across splits')
    device='cuda' if torch.cuda.is_available() and not args.cpu else 'cpu'
    tokenizer=AutoTokenizer.from_pretrained(args.backbone,use_fast=False)
    datasets={s:Reviews(v,tokenizer,args.max_length) for s,v in rows.items()}
    def collate(batch):
        tokens=tokenizer.pad([{k:v for k,v in x.items() if k not in ('acd','spc')} for x in batch],return_tensors='pt')
        tokens['acd']=torch.tensor(np.stack([x['acd'] for x in batch]))
        tokens['spc']=torch.tensor(np.stack([x['spc'] for x in batch]))
        return tokens
    loaders={s:DataLoader(ds,batch_size=args.batch_size,shuffle=s=='train',collate_fn=collate) for s,ds in datasets.items()}
    model=ABSA(args.backbone).to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.learning_rate,weight_decay=.01)
    print(json.dumps({'event':'training_started','device':device,'steps_per_epoch':len(loaders['train']),
                      'epochs':args.epochs,'threads':args.threads,'split_counts':{k:len(v) for k,v in rows.items()}}),flush=True)
    acd_loss=nn.BCEWithLogitsLoss(pos_weight=torch.tensor(args.acd_positive_weight,device=device))
    spc_loss=nn.BCEWithLogitsLoss(reduction='none')
    def forward(batch):
        a,p=model(**{k:v.to(device) for k,v in batch.items() if k not in ('acd','spc')})
        gold_a=batch['acd'].to(device);gold_p=batch['spc'].to(device)
        mask=gold_a.unsqueeze(-1).expand_as(gold_p)
        loss=acd_loss(a,gold_a)+args.spc_weight*(spc_loss(p,gold_p)*mask).sum()/mask.sum().clamp(min=1)
        return loss,a,p
    def evaluate(split):
        model.eval();pred=[]
        with torch.no_grad():
            for batch in loaders[split]:
                _,a,p=forward(batch)
                present=a.sigmoid()>=args.acd_threshold
                pred.extend(((p.sigmoid()>=args.spc_threshold)&present.unsqueeze(-1)).reshape(-1,15).cpu().numpy().astype(int))
        return metrics(datasets[split].spc.reshape(-1,15).astype(int),np.asarray(pred)),pred
    best=-1;history=[];bad=0
    for epoch in range(args.epochs):
        model.train();losses=[]
        optimizer.zero_grad()
        for step,batch in enumerate(loaders['train'],1):
            loss,_,_=forward(batch)
            group_start=((step-1)//args.accumulation)*args.accumulation
            divisor=min(args.accumulation,len(loaders['train'])-group_start)
            (loss/divisor).backward()
            if step%args.accumulation==0 or step==len(loaders['train']):
                nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step();optimizer.zero_grad()
            losses.append(float(loss.detach()))
            if step%25==0:
                progress={'epoch':epoch+1,'step':step,'steps':len(loaders['train']),
                          'train_loss':float(np.mean(losses)),'elapsed_seconds':round(time.perf_counter()-started,1)}
                dump(args.output_dir/'progress.json',progress);print(json.dumps(progress),flush=True)
        dev,_=evaluate('dev');history.append({'epoch':epoch+1,'train_loss':float(np.mean(losses)),'dev_macro_f1':dev['pair_macro_f1_15_labels']})
        print(json.dumps(history[-1]),flush=True)
        if dev['pair_macro_f1_15_labels']>best:
            best=dev['pair_macro_f1_15_labels'];bad=0
            torch.save({'weights':model.state_dict(),'backbone':args.backbone,'epoch':epoch+1,'dev':dev},args.output_dir/'best_checkpoint.pt')
        else:
            bad+=1
            if bad>=args.patience: break
    del optimizer
    checkpoint=torch.load(args.output_dir/'best_checkpoint.pt',map_location=device,weights_only=True)
    model.load_state_dict(checkpoint['weights'])
    del checkpoint
    test,pred=evaluate('test')
    torch.save({'weights':model.state_dict(),'backbone':args.backbone,'classes':CLASSES,
                'acd_threshold':args.acd_threshold,'spc_threshold':args.spc_threshold},args.output_dir/'model.pt')
    tokenizer.save_pretrained(args.output_dir/'tokenizer')
    report={'architecture':'PhoBERT two-head review-level ACD and masked SPC',
            'backbone':args.backbone,'seed':args.seed,'device':device,'split_counts':{k:len(v) for k,v in rows.items()},
            'backbone_revision':getattr(model.encoder.config,'_commit_hash',None),
            'history':history,'test':test,'selection':'best dev pair macro F1',
            'dataset_sha256':hashes,'torch_version':torch.__version__,
            'config':{k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
            'elapsed_seconds':time.perf_counter()-started,
            'test_status':'Fixed ViTASA split previously reported for SVM; no test-based tuning in this run',
            'limitation':'Review-level ViTASA label mapping; no span extraction; underthesea word segmentation.'}
    dump(args.output_dir/'metrics.json',report)
    dump(args.output_dir/'test_predictions.json',[
        {'id':r['id'],'gold':r['labels'],'predicted':[c for c,v in zip(CLASSES,p) if v]}
        for r,p in zip(rows['test'],pred)])
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path('data'))
    parser.add_argument('--output-dir',type=Path,default=Path('outputs/phobert_multitask'))
    parser.add_argument('--backbone',default='vinai/phobert-base')
    parser.add_argument('--epochs',type=int,default=3);parser.add_argument('--batch-size',type=int,default=4)
    parser.add_argument('--max-length',type=int,default=256);parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--learning-rate',type=float,default=2e-5)
    parser.add_argument('--acd-positive-weight',type=float,default=2)
    parser.add_argument('--spc-weight',type=float,default=1)
    parser.add_argument('--acd-threshold',type=float,default=.5)
    parser.add_argument('--spc-threshold',type=float,default=.5)
    parser.add_argument('--patience',type=int,default=2);parser.add_argument('--cpu',action='store_true')
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--accumulation',type=int,default=4)
    result=train(parser.parse_args())
    print(json.dumps({'test_macro_f1':result['test']['pair_macro_f1_15_labels'],'device':result['device']}))


if __name__=='__main__': main()
