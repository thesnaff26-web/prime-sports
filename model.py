"""Fixed Elo baseline; chronological evaluation, no optimization on test data."""
import math
from collections import defaultdict
VERSION = 'elo-v1'
THRESHOLD = .65

def probability(ratings, home, away):
    return 1 / (1 + 10 ** ((ratings[away] - ratings[home] - 45) / 400))

def wilson(wins, total):
    if not total: return 0
    z = 1.96
    p = wins / total
    return (p + z*z/(2*total) - z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))) / (1+z*z/total)

def train(games):
    ratings = defaultdict(lambda: 1500.)
    played = defaultdict(int)
    wins = samples = 0
    # Group entire UTC days: results within a day never inform that day forecasts.
    groups = defaultdict(list)
    for g in games: groups[g['date'][:10]].append(g)
    for date in sorted(groups):
        updates = []
        for g in groups[date]:
            h,a = g['home_id'],g['away_id']
            p = probability(ratings,h,a)
            outcome = g['home_score'] > g['away_score']
            if min(played[h],played[a]) >= 10 and max(p,1-p) >= THRESHOLD:
                samples += 1
                wins += int((p >= .5) == outcome)
            updates.append((h,a,24*(int(outcome)-p)))
        for h,a,delta in updates:
            ratings[h] += delta; ratings[a] -= delta
            played[h] += 1; played[a] += 1
    lower = wilson(wins,samples)
    metrics = dict(samples=samples,wins=wins,accuracy=wins/samples if samples else None,
                   lower95=lower,approved=samples >= 60 and lower > .5)
    return ratings,played,metrics
