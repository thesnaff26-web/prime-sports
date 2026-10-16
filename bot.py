"""Public sports feeds -> immutable pregame picks -> automatically settled archive."""
import datetime as dt
import json
import pathlib
import urllib.request
from khl_source import fetch_schedule
from model import train, probability, THRESHOLD, VERSION
UTC=dt.timezone.utc
ROOT=pathlib.Path(__file__).resolve().parent
DATA=ROOT/'data'

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'PRIME/3.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=25) as r: return json.load(r)

def nhl(day):
    games=[]
    for g in fetch('https://api-web.nhle.com/v1/score/'+day.isoformat()).get('games',[]):
        if g.get('gameType') != 2: continue
        h,a=g['homeTeam'],g['awayTeam']
        games.append(dict(id=str(g['id']),sport='NHL',date=g['startTimeUTC'],home=h.get('name',{}).get('default',h['abbrev']),away=a.get('name',{}).get('default',a['abbrev']),home_id=h['abbrev'],away_id=a['abbrev'],home_score=h.get('score'),away_score=a.get('score'),status='final' if g['gameState'] in ('OFF','FINAL') else 'pre' if g['gameState'] in ('FUT','PRE') else 'live'))
    return games

def load(name,default):
    p=DATA/name
    return json.loads(p.read_text()) if p.exists() else default

def save(name,value):
    p=DATA/name; tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)

def timestamp(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(UTC)

def run():
    DATA.mkdir(exist_ok=True)
    now=dt.datetime.now(UTC);today=now.date()
    state=load('state.json',{'games':{},'predictions':{},'cursors':{}})
    report={'updated_at':now.isoformat(),'model':VERSION,'leagues':{},'predictions':[],'fixtures':[],'errors':[]}
    for league in ('NHL','KHL'):
        try:
            season=dt.date(today.year if today.month>=9 else today.year-1,9,1)
            cursor=max(season,dt.date.fromisoformat(state['cursors'].get(league,season.isoformat()))-dt.timedelta(days=2))
            received={}
            day=cursor
            while day<=today+dt.timedelta(days=3):
                span=min(7,(today+dt.timedelta(days=4)-day).days) if league=='KHL' else 1
                batch=fetch_schedule(day,days=span) if league=='KHL' else nhl(day)
                for g in batch:
                    if not g.get('home_id') or not g.get('away_id'): continue
                    g['date']=timestamp(g['date']).isoformat()
                    received[g['id']]=g
                day+=dt.timedelta(days=span)
            # Commit source cursor only after the complete requested range succeeds.
            for g in received.values():
                if g['status']=='final' and all(type(g.get(k)) is int for k in ('home_score','away_score')) and g['home_score']!=g['away_score'] and timestamp(g['date'])<now:
                    state['games'][league+':'+g['id']]=g
            state['cursors'][league]=today.isoformat()
            history=[g for g in state['games'].values() if g['sport']==league and timestamp(g['date']).date()>=season and timestamp(g['date'])+dt.timedelta(hours=6)<now]
            ratings,played,metrics=train(history)
            report['leagues'][league]={**metrics,'games':len(history),'status':'ready' if metrics['approved'] else 'learning'}
            # Results are looked up by stable league + event ID, never by team text.
            for key,p in state['predictions'].items():
                g=state['games'].get(key)
                if p['status']=='pending' and g:
                    winner=g['home_id'] if g['home_score']>g['away_score'] else g['away_id']
                    p.update(status='settled',result='win' if winner==p['pick_id'] else 'loss',score=f"{g['home_score']} : {g['away_score']}",settled_at=now.isoformat())
            for g in received.values():
                hours=(timestamp(g['date'])-now).total_seconds()/3600
                if g['status']!='pre' or not 2<=hours<=72: continue
                report['fixtures'].append(g)
                key=league+':'+g['id']
                if key in state['predictions'] or not metrics['approved']: continue
                if min(played[g['home_id']],played[g['away_id']])<10: continue
                p=probability(ratings,g['home_id'],g['away_id'])
                if max(p,1-p)<THRESHOLD: continue
                home=p>=.5
                state['predictions'][key]={**g,'key':key,'pick':g['home'] if home else g['away'],'pick_id':g['home_id'] if home else g['away_id'],'estimate':max(p,1-p),'model':VERSION,'published_at':now.isoformat(),'status':'pending','result':None}
        except Exception as exc:
            report['errors'].append(league+': '+type(exc).__name__+': '+str(exc)[:180])
            report['leagues'][league]={'status':'error'}
    report['predictions']=sorted(state['predictions'].values(),key=lambda p:p['published_at'],reverse=True)
    save('state.json',state);save('feed.json',report)
    print(json.dumps({'leagues':report['leagues'],'errors':report['errors']},ensure_ascii=False))
    if report['errors']: raise SystemExit(1)
if __name__=='__main__':run()
