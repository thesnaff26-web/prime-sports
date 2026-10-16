"""KHL mobile-api fixture adapter. Source availability must be verified in Actions.

The API is undocumented by its operator; if its schema changes, fail visibly.
No data from this adapter is used to publish unvalidated picks.
"""
import datetime as dt
import json
import urllib.parse
import urllib.request

BASE = 'https://khl.api.webcaster.pro/api/khl_mobile/events_v2.json'
UTC = dt.timezone.utc


def _unwrap(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError('KHL API returned unexpected top-level type')
    for key in ('events', 'items', 'results', 'data'):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            try:
                return _unwrap(value)
            except ValueError:
                pass
    raise ValueError('KHL API response has no recognized events list; keys=' + ','.join(payload.keys()))


def _name(team):
    if isinstance(team, str):
        return team
    if isinstance(team, dict):
        for key in ('name', 'short_name', 'title', 'full_name'):
            val = team.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                result = val.get('ru') or val.get('default')
                if isinstance(result, str):
                    return result
    return None


def _timestamp(value):
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000 if value > 10**11 else value, UTC)
    if isinstance(value, str):
        if value.isdigit():
            return _timestamp(int(value))
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('KHL kickoff has no timezone')
        return parsed.astimezone(UTC)
    raise ValueError('KHL kickoff missing or invalid')


def normalize(raw):
    if not isinstance(raw, dict):
        return None
    event_id = raw.get('id')
    home = raw.get('team_a') or raw.get('home_team') or raw.get('home')
    away = raw.get('team_b') or raw.get('away_team') or raw.get('away')
    if not event_id or not _name(home) or not _name(away):
        return None
    start = _timestamp(raw.get('start_at') or raw.get('start_time') or raw.get('date'))
    status = str(raw.get('status') or raw.get('state') or '').lower()
    # Status varies by API revision; treat unknown as pre only when kickoff is in future.
    if any(term in status for term in ('finish', 'final', 'ended', 'completed')):
        state = 'final'
    elif any(term in status for term in ('live', 'progress', 'period')):
        state = 'live'
    else:
        state = 'pre' if start > dt.datetime.now(UTC) else 'unknown'
    return {
        'id': str(event_id), 'sport': 'KHL', 'date': start.isoformat(),
        'home': _name(home), 'away': _name(away),
        'home_id': str(home.get('id')) if isinstance(home, dict) and home.get('id') else None,
        'away_id': str(away.get('id')) if isinstance(away, dict) and away.get('id') else None,
        'home_rate': None, 'away_rate': None, 'status': state,
        'home_score': raw.get('team_a_score') or raw.get('home_score'),
        'away_score': raw.get('team_b_score') or raw.get('away_score'),
    }


def fetch_schedule(start_day, days=8):
    start = dt.datetime.combine(start_day, dt.time.min, UTC)
    end = start + dt.timedelta(days=days)
    params = {
        'locale': 'ru', 'order_direction': 'asc',
        'q[start_at_gt_time_from_unixtime]': int(start.timestamp()) - 1,
        'q[start_at_lt_time_from_unixtime]': int(end.timestamp()),
    }
    events = {}
    for page in range(1, 11):
        query = urllib.parse.urlencode({**params, 'page': page})
        request = urllib.request.Request(BASE + '?' + query, headers={
            'Accept': 'application/json', 'User-Agent': 'PRIME-Sports/2.1',
        })
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = json.load(response)
        batch = _unwrap(raw)
        if not batch:
            break
        valid = 0
        for item in batch:
            try:
                event = normalize(item)
            except (ValueError, OverflowError, TypeError):
                continue
            if event:
                valid += 1
                kickoff = _timestamp(event['date'])
                if start <= kickoff < end:
                    events[event['id']] = event
        if valid == 0:
            raise ValueError('KHL API returned entries but none could be normalized; sample keys=' + str(list(batch[0]) if isinstance(batch[0], dict) else type(batch[0])))
        if len(batch) < 16:
            break
    return sorted(events.values(), key=lambda x: x['date'])
