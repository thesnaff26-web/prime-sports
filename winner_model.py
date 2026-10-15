"""PRIME 1.8: current-season, strictly chronological winner model and audit.

Probabilities are research estimates, never guarantees. No model is allowed to
publish without a meaningful out-of-sample improvement over a baseline.
"""
from collections import defaultdict
import math

MIN_HISTORY = 180
MIN_TEST = 80
MIN_TEAM_GAMES = 8
MIN_BRIER_GAIN = 0.01
MIN_CONFIDENCE = 0.70


def _sigmoid(x):
    return 1 / (1 + math.exp(-max(-30, min(30, x))))


def estimate(games, home, away):
    stats = defaultdict(lambda: [0, 0])
    home_wins = 0
    for g in games:
        h, a = g['home'], g['away']
        stats[h][1] += 1
        stats[a][1] += 1
        if g['hs'] > g['aws']:
            stats[h][0] += 1
            home_wins += 1
        elif g['aws'] > g['hs']:
            stats[a][0] += 1
    if (stats[home][1] < MIN_TEAM_GAMES or
            stats[away][1] < MIN_TEAM_GAMES or len(games) < 30):
        return None
    # Beta-smoothed team win rates and shrunk league-wide home advantage.
    def rate(team):
        wins, played = stats[team]
        return (wins + 5) / (played + 10)
    h, a = rate(home), rate(away)
    league_home = (home_wins + 25) / (len(games) + 50)
    # Log-odds difference: equal-strength teams have league home win probability.
    logit = lambda p: math.log(p / (1 - p))
    return _sigmoid(logit(h) - logit(a) + logit(league_home))


def validate(games):
    if len(games) < MIN_HISTORY:
        return False, {'reason': 'insufficient_current_season_games',
                       'current': len(games), 'required': MIN_HISTORY}
    rows = []
    for i in range(max(80, len(games)//2), len(games)):
        g = games[i]
        p = estimate(games[:i], g['home'], g['away'])
        if p is None:
            continue
        y = int(g['hs'] > g['aws'])
        # Baseline uses only past matches, no future information.
        prior = games[:i]
        base = (sum(t['hs'] > t['aws'] for t in prior) + 25) / (len(prior) + 50)
        rows.append((p, base, y))
    if len(rows) < MIN_TEST:
        return False, {'reason': 'insufficient_out_of_sample_games',
                       'tested': len(rows), 'required': MIN_TEST}
    brier = sum((p-y)**2 for p,b,y in rows)/len(rows)
    baseline = sum((b-y)**2 for p,b,y in rows)/len(rows)
    approved = brier + MIN_BRIER_GAIN < baseline
    return approved, {'reason': 'approved' if approved else 'no_meaningful_baseline_improvement',
                      'tested': len(rows), 'brier': round(brier, 4),
                      'baseline_brier': round(baseline, 4),
                      'min_brier_gain': MIN_BRIER_GAIN}


def pick(games, home, away):
    p = estimate(games, home, away)
    if p is None:
        return None
    return {'pick_home': p >= .5, 'probability': round(max(p, 1-p), 3),
            'home_probability': round(p, 3),
            'method': 'prime18_current_season_walkforward'}
