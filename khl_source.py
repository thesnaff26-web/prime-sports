"""KHL fixture discovery adapter. Fail loudly on unknown response schemas.

KHL picks are NOT published by this module. It only provides fixtures.
"""
import datetime as dt
import json
import urllib.parse
import urllib.request

BASE = 'https://khl.api.webcaster.pro/api/khl_mobile/events_v2.json'
UTC = dt.timezone.utc
MSK = dt.timezone(dt.timedelta(hours=3))


def _unwrap(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ('events', 'items', 'results', 'data'):
            value = payload.get(key)
            if isinstance(value, (dict, list)):
                try:
                    return _unwrap(value)
                except ValueError:
                    pass
    raise ValueError('KHL API response has no recognized events list; keys=' + str(list(payload) if isinstance(payload, dict) else type(payload)))


def _value(obj, *keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        v = obj.get(key)
        if v is not None and v != '':
            return v
    return None


def _name(team):
    if isinstance(team, str):
        return team.strip() or None
    if isinstance(team, dict):
        for key in ('name', 'short_name', 'title', 'full_name', 'name_ru', 'shortname', 'team_name'):
            val = team.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                for lang in ('ru', 'default', 'en'):
                    if isinstance(val.get(lang), str) and val[lang].strip():
                        return val[lang].strip()
    return None


def _timestamp(value):
    if isinstance(value, dict):
        value = _value(value, 'timestamp', 'value', 'iso', 'date')
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000 if value > 10**11 else value, UTC)
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            return _timestamp(int(value))
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            # Unqualified KHL local match times are treated as Moscow time.
            parsed = parsed.replace(tzinfo=MSK)
        return parsed.astimezone(UTC)
    raise ValueError('KHL kickoff missing or invalid')


def _teams(event):
    home = _value(event, 'team_a', 'home_team', 'home', 'team1', 'team_1', 'homeTeam')
    away = _value(event, 'team_b', 'away_team', 'away', 'team2', 'team_2', 'awayTeam')
    if not (home and away):
        participants = _value(event, 'teams', 'participants', 'competitors')
        if isinstance(participants, dict):
            home = home or _value(participants, 'home', 'team_a', 'team1')
            away = away or _value(participants, 'away', 'team_b', 'team2')
        elif isinstance(participants, list) and len(participants) == 2:
            home = home or participants[0]
            away = away or participants[1]
    return home, away


def normalize(raw):
    if not isinstance(raw, dict):
        return None
    # The live response seen in GitHub Actions contains wrappers {"event": {...}}.
    event = raw.get('event')
    if isinstance(event, dict):
        event = {**raw, **event}
    else:
        event = raw
    event_id = _value(event, 'id', 'event_id', 'game_id', 'match_id')
    home, away = _teams(event)
    home_name, away_name = _name(home), _name(away)
    if not event_id or not home_name or not away_name or home_name == away_name:
        return None
    start_raw = _value(event, 'start_at', 'start_time', 'starts_at', 'date_time', 'datetime', 'date', 'startAt')
    start = _timestamp(start_raw)
    status = str(_value(event, 'status', 'state', 'game_status') or '').lower()
    if any(term in status for term in ('finish', 'final', 'ended', 'completed')):
        state = 'final'
    elif any(term in status for term in ('live', 'progress', 'period')):
        state = 'live'
    else:
        state = 'pre' if start > dt.datetime.now(UTC) else 'unknown'
    return {
        'id': str(event_id), 'sport': 'KHL', 'date': start.isoformat(),
        'home': home_name, 'away': away_name,
        'home_id': str(home.get('id')) if isinstance(home, dict) and home.get('id') is not None else None,
        'away_id': str(away.get('id')) if isinstance(away, dict) and away.get('id') is not None else None,
        'home_rate': None, 'away_rate': None, 'status': state,
        'home_score': _value(event, 'team_a_score', 'home_score'),
        'away_score': _value(event, 'team_b_score', 'away_score'),
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
            'Accept': 'application/json', 'User-Agent': 'PRIME-Sports/2.2',
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
            first = batch[0] if isinstance(batch[0], dict) else {}
            nested = first.get('event') if isinstance(first.get('event'), dict) else {}
            raise ValueError('KHL API entries not normalized; top_keys=' + str(list(first)) + '; event_keys=' + str(list(nested))[:700])
        if len(batch) < 16:
            break
    return sorted(events.values(), key=lambda x: x['date'])
