"""Prompt locally; never echo or package a user's key."""
from getpass import getpass
from pathlib import Path
import re

if __name__=='__main__':
    path=Path(__file__).resolve().parent.parent/'.env'
    existing={}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                name,value=line.split('=',1);existing[name.strip()]=value.strip()
    serp=getpass('SerpApi key (hidden, Enter = keep current): ').strip() or existing.get('SERPAPI_API_KEY','')
    gemini=getpass('Gemini API key (hidden, Enter = keep/skip): ').strip() or existing.get('GEMINI_API_KEY','')
    for name,key in [('SerpApi',serp),('Gemini',gemini)]:
        if key and not re.fullmatch(r'[A-Za-z0-9_-]{20,250}',key):
            raise SystemExit(f'Invalid {name} key format. No changes made.')
    values={'SERPAPI_API_KEY':serp,'SERPAPI_DAILY_LIMIT':existing.get('SERPAPI_DAILY_LIMIT','30'),
            'GEMINI_API_KEY':gemini,'GEMINI_MODEL':existing.get('GEMINI_MODEL','gemini-2.5-flash')}
    path.write_text(''.join(f'{k}={v}\n' for k,v in values.items()),encoding='utf-8')
    print('Saved locally. Restart web. Do not share .env.')
