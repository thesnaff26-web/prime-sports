"""PRIME 1.5: NHL totals research model; conservative, time-ordered validation."""
import datetime as dt
import math
from collections import defaultdict

LINES = (3.5, 4.5, 5.5, 6.5, 7.5)

def over_probability(lam, line):
    term = math.exp(-lam)
    cdf = term
    for k in range(1, int(line) + 1):
        term *= lam / k
        cdf += term
    return max(0., min(1., 1. - cdf))

def _season_start(today):
    return dt.date(today.year if today.month >= 10 else today.year - 1, 10, 1)

def _fetch_range(fetch, first, last, label):
    seen = {}
    day = first
    errors = 0
    while day < last:
        try:
            for g in fetch('https://api-web.nhle.com/v1/score/' + day.isoformat()).get('games', []):
                h, a = g.get('homeTeam') or {}, g.get('awayTeam') or {}
                if (g.get('gameState') in ('FINAL', 'OFF') and
                    isinstance(h.get('score'), int) and isinstance(a.get('score'), int) and
                    h.get('abbrev') and a.get('abbrev') and g.get('gameType') == 2):
                    seen[str(g['id'])] = {'date':g.get('startTimeUTC') or day.isoformat(),
                        'home':h['abbrev'], 'away':a['abbrev'],
                        'hs':h['score'], 'aws':a['score']}
        except Exception as exc:
            errors += 1
            if errors <= 3: print('History fetch skipped', day, str(exc)[:90])
        day += dt.timedelta(days=1)
    print(f'History {label}: {len(seen)} games, {errors} failed days')
    return sorted(seen.values(), key=lambda g:g['date'])

def history(fetch, today):
    current = _season_start(today)
    # Last ~100 regular-season days of the preceding season; avoid playoffs.
    previous = current.replace(year=current.year-1)
    previous_end = dt.date(previous.year+1, 4, 18)
    prev = _fetch_range(fetch, previous_end-dt.timedelta(days=100), previous_end, 'previous')
    recent = _fetch_range(fetch, max(current, today-dt.timedelta(days=70)), today, 'current')
    return prev, recent

def estimate(previous, current, home, away):
    if len(previous) < 100: return None
    # Regular-season home/away attack and defense; shrink toward league averages.
    # Previous-season observations carry reduced weight, current season takes priority.
    stats = defaultdict(lambda: [0.,0.,0.,0.])
    total_goals = 0.
    total_weight = 0.
    for weight, games in ((0.4, previous), (1., current)):
        for g in games:
            h,a = g['home'],g['away']
            hs,aws = g['hs'],g['aws']
            for team, scored, conceded in ((h,hs,aws),(a,aws,hs)):
                s=stats[team]
                s[0]+=weight*scored;s[1]+=weight*conceded;s[2]+=weight
                if team==h:s[3]+=weight
            total_goals+=weight*(hs+aws)
            total_weight+=weight
    if total_weight<=0:return None
    league_goals=total_goals/(2*total_weight)
    # No team-specific estimates without at least some observations.
    if stats[home][2]<2 or stats[away][2]<2:return None
    def rates(team):
        gf,ga,n,_=stats[team]
        prior=12.
        return ((gf+prior*league_goals)/(n+prior),
                (ga+prior*league_goals)/(n+prior))
    hf,ha=rates(home);af,aa=rates(away)
    home_adv=0.13  # small fixed adjustment, not an estimated advantage
    lam=(hf+aa)/2+(af+ha)/2
    return max(3.,min(8.5,lam+home_adv))

def validate(previous, current):
    # Strict chronological out-of-sample evaluation; no current test game in training.
    if len(previous)<100 or len(current)<60:
        return [], {'reason':'insufficient_samples', 'previous':len(previous),'current':len(current)}
    start=max(30,len(current)//2)
    tested=[]
    for i in range(start,len(current)):
        g=current[i]
        lam=estimate(previous,current[:i],g['home'],g['away'])
        if lam is not None:tested.append((lam,g['hs']+g['aws']))
    if len(tested)<30:
        return [], {'reason':'insufficient_test_games','tested':len(tested)}
    accepted=[]; metrics={}
    for line in LINES:
        # Baseline uses only previous season and training portion of current season.
        train=previous+current[:start]
        baseline=sum(g['hs']+g['aws']>line for g in train)/len(train)
        brier=sum((over_probability(lam,line)-int(total>line))**2 for lam,total in tested)/len(tested)
        base=sum((baseline-int(total>line))**2 for _,total in tested)/len(tested)
        metrics[str(line)]={'brier':round(brier,4),'baseline_brier':round(base,4),'tested':len(tested)}
        # Require measurable improvement, not a rounding tie.
        if brier+0.005<base:accepted.append(line)
    return accepted, metrics

def enrich(predictions, previous, current, lines):
    count=0
    for p in predictions.values():
        if p.get('sport')!='NHL' or p.get('status')!='pending' or p.get('totals'):continue
        lam=estimate(previous,current,p.get('home_id'),p.get('away_id'))
        if lam is None:continue
        for line in lines:
            over=over_probability(lam,line)
            side,prob=('over',over) if over>=.5 else ('under',1-over)
            if prob<.65:continue
            p.setdefault('totals',[]).append({'market_type':'total','total_line':line,'total_side':side,
                'market_label':('Тотал больше ' if side=='over' else 'Тотал меньше ')+str(line).replace('.',','),
                'probability':round(prob,3),'probability_method':'poisson_v16_research_validated'})
            count+=1
    return count
