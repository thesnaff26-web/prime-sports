"""Optional exploratory NHL totals with chronological validation."""
import datetime as dt
import math
from collections import defaultdict

def over_probability(lam, line):
    term = math.exp(-lam)
    cdf = term
    for k in range(1, int(line)+1):
        term *= lam/k
        cdf += term
    return max(0., min(1., 1.-cdf))

def estimate(games, home, away):
    by_team = defaultdict(list)
    for g in games:
        by_team[g['home']].append(g['hs'])
        by_team[g['away']].append(g['aws'])
    if len(games)<45 or len(by_team[home])<5 or len(by_team[away])<5:
        return None
    mean = sum(g['hs']+g['aws'] for g in games)/len(games)
    h = (sum(by_team[home])+3*mean)/(len(by_team[home])+6)
    a = (sum(by_team[away])+3*mean)/(len(by_team[away])+6)
    return max(2.5,min(9.,h+a))

def history(fetch, today):
    season = dt.date(today.year if today.month>=10 else today.year-1,10,1)
    first=max(season,today-dt.timedelta(days=42))
    seen={}
    day=first
    while day<today:
        try:
            for g in fetch('https://api-web.nhle.com/v1/score/'+day.isoformat()).get('games',[]):
                h,a=g.get('homeTeam',{}),g.get('awayTeam',{})
                if g.get('gameState') in ('FINAL','OFF') and isinstance(h.get('score'),int) and isinstance(a.get('score'),int) and h.get('abbrev') and a.get('abbrev'):
                    seen[str(g['id'])]={'date':g.get('startTimeUTC',''),'home':h['abbrev'],'away':a['abbrev'],'hs':h['score'],'aws':a['score']}
        except Exception as exc:
            print('History fetch skipped',day,str(exc)[:100])
        day+=dt.timedelta(days=1)
    return sorted(seen.values(),key=lambda g:g['date'])

def validated_lines(games):
    if len(games)<85:return []
    start=max(60,int(len(games)*.75))
    tested=[]
    for i in range(start,len(games)):
        g=games[i]
        lam=estimate(games[:i],g['home'],g['away'])
        if lam is not None:tested.append((lam,g['hs']+g['aws']))
    if len(tested)<20:return []
    accepted=[]
    for line in (4.5,5.5,6.5):
        baseline=sum(g['hs']+g['aws']>line for g in games[:start])/start
        brier=sum((over_probability(lam,line)-(total>line))**2 for lam,total in tested)/len(tested)
        base=sum((baseline-(total>line))**2 for _,total in tested)/len(tested)
        if brier<base:accepted.append(line)
    return accepted

def enrich(predictions,games,lines):
    count=0
    for p in predictions.values():
        if p.get('sport')!='NHL' or p.get('status')!='pending' or p.get('totals'):continue
        lam=estimate(games,p.get('home_id'),p.get('away_id'))
        if lam is None:continue
        for line in lines:
            over=over_probability(lam,line)
            side,prob=('over',over) if over>=.5 else ('under',1-over)
            if prob<.62:continue
            p.setdefault('totals',[]).append({'market_type':'total','total_line':line,'total_side':side,'market_label':('Тотал больше ' if side=='over' else 'Тотал меньше ')+str(line).replace('.',','),'probability':round(prob,3),'probability_method':'poisson_exploratory'})
            count+=1
    return count
