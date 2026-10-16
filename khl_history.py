"""Incremental KHL completed-game collection. Does not publish betting picks."""
import datetime as dt
import json
from pathlib import Path
from khl_source import fetch_schedule

UTC = dt.timezone.utc
HISTORY_PATH = Path('data/khl_history.json')


def _score(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = int(value)
        return n if n >= 0 and str(value).strip() == str(n) else None
    except (TypeError, ValueError):
        return None


def completed(event, now=None):
    now = now or dt.datetime.now(UTC)
    try:
        kickoff = dt.datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
        if kickoff.tzinfo is None:
            return None
    except (KeyError, ValueError, TypeError):
        return None
    if event.get('status') != 'final' or kickoff >= now:
        return None
    home, away = _score(event.get('home_score')), _score(event.get('away_score'))
    if home is None or away is None or home == away:
        # A final hockey score must have a winner; missing shootout winner is not safe.
        return None
    if not event.get('home') or not event.get('away') or not event.get('id'):
        return None
    return {'id': str(event['id']), 'date': kickoff.astimezone(UTC).isoformat(),
            'home': event['home'], 'away': event['away'],
            'home_id': event.get('home_id'), 'away_id': event.get('away_id'),
            'home_score': home, 'away_score': away, 'sport': 'KHL'}


def collect(today=None, lookback_days=None):
    # Backfill the 2026/27 regular season beginning September 1, 2026.
    # Subsequent hourly runs are idempotent by provider event ID.
    today = today or dt.datetime.now(UTC).date()
    if lookback_days is None:
        season_start = dt.date(today.year if today.month >= 8 else today.year - 1, 9, 1)
        lookback_days = max(0, (today - season_start).days)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if HISTORY_PATH.exists():
        payload = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
        if not isinstance(payload, dict) or not isinstance(payload.get('games', {}), dict):
            raise ValueError('Invalid existing KHL history; refusing to overwrite')
    else:
        payload = {'version': 1, 'games': {}}
    games = payload['games']
    # Backfill recent games in 7-day batches, then append fresh results hourly.
    # Query end is exclusive. Never invent a result when the API omits one.
    discovered = 0
    added = 0
    statuses = {}
    score_samples = []
    for offset in range(lookback_days, -1, -7):
        start = today - dt.timedelta(days=offset)
        days = min(7, (today - start).days + 1)
        fixtures = fetch_schedule(start, days=days)
        discovered += len(fixtures)
        for event in fixtures:
            status = str(event.get('status', 'missing'))
            raw_status = str(event.get('raw_status', ''))
            statuses[(status, raw_status)] = statuses.get((status, raw_status), 0) + 1
            if len(score_samples) < 5 and event.get('status') == 'unknown':
                score_samples.append({'date': event.get('date'), 'status': raw_status,
                                      'home_score': event.get('home_score'),
                                      'away_score': event.get('away_score')})
            game = completed(event)
            if game is None:
                continue
            if game['id'] not in games:
                added += 1
            games[game['id']] = game
    payload['updated_at'] = dt.datetime.now(UTC).isoformat()
    payload['games'] = dict(sorted(games.items(), key=lambda pair: (pair[1]['date'], pair[0])))
    HISTORY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'KHL history: API fixtures={discovered}, new final={added}, stored final={len(games)}')
    print('KHL diagnostic status counts:', sorted(((str(k), v) for k, v in statuses.items()), key=lambda x: -x[1])[:20])
    if score_samples:
        print('KHL diagnostic unknown examples:', json.dumps(score_samples, ensure_ascii=False))
    return payload


def team_stats(games):
    stats = {}
    for game in games.values():
        for side, other in [('home', 'away'), ('away', 'home')]:
            team = game.get(side + '_id') or game[side]
            row = stats.setdefault(str(team), {'name': game[side], 'played': 0, 'wins': 0, 'losses': 0, 'gf': 0, 'ga': 0})
            row['played'] += 1
            row['wins'] += int(game[side + '_score'] > game[other + '_score'])
            row['losses'] += int(game[side + '_score'] < game[other + '_score'])
            row['gf'] += game[side + '_score']
            row['ga'] += game[other + '_score']
    return stats


if __name__ == '__main__':
    result = collect()
    print('KHL teams with results:', len(team_stats(result['games'])))
    print('KHL publishing: DISABLED until out-of-sample validation')
