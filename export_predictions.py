#!/usr/bin/env python3
"""Export ICE EDGE state into PRIME public feed. No Telegram credentials included."""
import datetime as dt
import json
import pathlib
import sys
source = pathlib.Path(sys.argv[1] if len(sys.argv)>1 else 'data/state.json')
out = pathlib.Path(__file__).parent/'data'/'predictions.json'
if not source.exists():
    raise SystemExit(f'State file missing: {source}')
state = json.loads(source.read_text(encoding='utf-8'))
records = state.get('predictions', {})
if not isinstance(records, dict):
    raise SystemExit('Expected predictions dictionary in state')
allowed = ('id','sport','date','home','away','pick','edge','home_rate','away_rate','status','result','score')
items = [{k:p[k] for k in allowed if k in p} for p in records.values() if isinstance(p,dict) and p.get('sport','NHL')=='NHL']
items.sort(key=lambda p:p.get('date') or '', reverse=True)
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'predictions':items},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Exported {len(items)} predictions to {out}')
