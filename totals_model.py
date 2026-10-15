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
    start = _season_start(today)
    current = _fetch_range(fetch, start, today, 'current')
    return [], current

def estimate(previous, current, home, away):
    # Strictly current-season data; prior season is intentionally ignored.
    stats = defaultdict(lambda: [0., 0., 0])
    goals = 0
    for g in current:
        hs, aws = g['hs'], g['aws']
        for team, scored, conceded in ((g['home'], hs, aws), (g['away'], aws, hs)):
            row = stats[team]
            row[0] += scored
            row[1] += conceded
            row[2] += 1
        goals += hs + aws
    if not current or stats[home][2] < 5 or stats[away][2] < 5:
        return None
    league_avg = goals / (2 * len(current))
    def rates(team):
        gf, ga, n = stats[team]
        prior = 12
        return ((gf + prior * league_avg) / (n + prior),
                (ga + prior * league_avg) / (n + prior))
    hf, ha = rates(home)
    af, aa = rates(away)
    lam = (hf + aa + af + ha) / 2
    return max(3., min(8.5, lam))

def validate(previous, current):
    # Walk-forward testing on CURRENT season only, no test-game leakage.
    # Conservative minimum to avoid advertising unstable early-season results.
    if len(current) < 180:
        return [], {'reason': 'insufficient_current_season_games', 'current': len(current), 'required': 180}
    start = max(80, len(current) // 2)
    tested = []
    for i in range(start, len(current)):
        game = current[i]
        lam = estimate([], current[:i], game['home'], game['away'])
        if lam is None:
            continue
        baseline_train = current[:i]
        tested.append((lam, game['hs'] + game['aws'], baseline_train))
    if len(tested) < 80:
        return [], {'reason': 'insufficient_out_of_sample_games', 'tested': len(tested), 'required': 80}
    approved, metrics = [], {}
    for line in LINES:
        brier = sum((over_probability(lam, line) - int(total > line))**2
                    for lam, total, train in tested) / len(tested)
        baseline = sum(((sum(g['hs'] + g['aws'] > line for g in train) / len(train)) - int(total > line))**2
                       for lam, total, train in tested) / len(tested)
        metrics[str(line)] = {'brier': round(brier, 4), 'baseline_brier': round(baseline, 4), 'tested': len(tested)}
        if brier + 0.01 < baseline:
            approved.append(line)
    return approved, metrics

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
                'probability':round(prob,3),'probability_method':'poisson_v17_current_season_walkforward'})
            count+=1
    return count
