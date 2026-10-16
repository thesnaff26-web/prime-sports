#!/usr/bin/env python3
"""ICE EDGE: NHL photo forecasts with auditable Telegram publication records."""
import datetime as dt
from collections import Counter
from totals_model import history, validate, enrich
from winner_model import validate as validate_winners, pick as winner_pick, MIN_CONFIDENCE
from khl_source import fetch_schedule as fetch_khl_schedule
import json
import os
import pathlib
import subprocess
import urllib.parse
import urllib.request
import io
import random
import re
import time
from PIL import Image, ImageDraw, ImageFont, ImageFilter

UTC = dt.timezone.utc
MSK = dt.timezone(dt.timedelta(hours=3))
RU_TEAMS = {
    "Boston Bruins": "Бостон Брюинз", "Philadelphia Flyers": "Филадельфия Флайерз",
    "Chicago Blackhawks": "Чикаго Блэкхокс", "Carolina Hurricanes": "Каролина Харрикейнз",
    "New York Rangers": "Нью-Йорк Рейнджерс", "New York Islanders": "Нью-Йорк Айлендерс",
    "New Jersey Devils": "Нью-Джерси Девилз", "Washington Capitals": "Вашингтон Кэпиталз",
    "Pittsburgh Penguins": "Питтсбург Пингвинз", "Columbus Blue Jackets": "Коламбус Блю Джекетс",
    "Buffalo Sabres": "Баффало Сейбрз", "Detroit Red Wings": "Детройт Ред Уингз",
    "Ottawa Senators": "Оттава Сенаторз", "Montreal Canadiens": "Монреаль Канадиенс",
    "Toronto Maple Leafs": "Торонто Мейпл Лифс", "Tampa Bay Lightning": "Тампа-Бэй Лайтнинг",
    "Florida Panthers": "Флорида Пантерз", "Nashville Predators": "Нэшвилл Предаторз",
    "St. Louis Blues": "Сент-Луис Блюз", "Minnesota Wild": "Миннесота Уайлд",
    "Winnipeg Jets": "Виннипег Джетс", "Dallas Stars": "Даллас Старз",
    "Colorado Avalanche": "Колорадо Эвеланш", "Utah Mammoth": "Юта Маммот",
    "Utah Hockey Club": "Юта", "Arizona Coyotes": "Аризона Койотис",
    "Vegas Golden Knights": "Вегас Голден Найтс", "Los Angeles Kings": "Лос-Анджелес Кингз",
    "Anaheim Ducks": "Анахайм Дакс", "San Jose Sharks": "Сан-Хосе Шаркс",
    "Seattle Kraken": "Сиэтл Кракен", "Vancouver Canucks": "Ванкувер Кэнакс",
    "Edmonton Oilers": "Эдмонтон Ойлерз", "Calgary Flames": "Калгари Флэймз",
}

# NHL team abbreviations are more stable than the API display names.
RU_BY_CODE = {
    'ANA': 'Анахайм Дакс', 'BOS': 'Бостон Брюинз',
    'BUF': 'Баффало Сейбрз', 'CAR': 'Каролина Харрикейнз',
    'CBJ': 'Коламбус Блю Джекетс', 'CGY': 'Калгари Флэймз',
    'CHI': 'Чикаго Блэкхокс', 'COL': 'Колорадо Эвеланш',
    'DAL': 'Даллас Старз', 'DET': 'Детройт Ред Уингз',
    'EDM': 'Эдмонтон Ойлерз', 'FLA': 'Флорида Пантерз',
    'LAK': 'Лос-Анджелес Кингз', 'MIN': 'Миннесота Уайлд',
    'MTL': 'Монреаль Канадиенс', 'NJD': 'Нью-Джерси Девилз',
    'NSH': 'Нэшвилл Предаторз', 'NYI': 'Нью-Йорк Айлендерс',
    'NYR': 'Нью-Йорк Рейнджерс', 'OTT': 'Оттава Сенаторз',
    'PHI': 'Филадельфия Флайерз', 'PIT': 'Питтсбург Пингвинз',
    'SEA': 'Сиэтл Кракен', 'SJS': 'Сан-Хосе Шаркс',
    'STL': 'Сент-Луис Блюз', 'TBL': 'Тампа-Бэй Лайтнинг',
    'TOR': 'Торонто Мейпл Лифс', 'UTA': 'Юта Маммот',
    'VAN': 'Ванкувер Кэнакс', 'VGK': 'Вегас Голден Найтс',
    'WPG': 'Виннипег Джетс', 'WSH': 'Вашингтон Кэпиталз',
}
# Handle older predictions saved with short English names.
RU_ALIASES = dict(RU_TEAMS)
for english, russian in RU_TEAMS.items():
    RU_ALIASES.setdefault(english.split(' ')[-1], russian)
RU_ALIASES.update({
    'Rangers': RU_BY_CODE['NYR'], 'Islanders': RU_BY_CODE['NYI'],
    'Devils': RU_BY_CODE['NJD'], 'Blue Jackets': RU_BY_CODE['CBJ'],
    'Red Wings': RU_BY_CODE['DET'], 'Maple Leafs': RU_BY_CODE['TOR'],
    'Golden Knights': RU_BY_CODE['VGK'], 'Kings': RU_BY_CODE['LAK'],
    'Blackhawks': RU_BY_CODE['CHI'], 'Hurricanes': RU_BY_CODE['CAR'],
    'Canucks': RU_BY_CODE['VAN'], 'Flyers': RU_BY_CODE['PHI'],
    'Utah Mammoth': RU_BY_CODE['UTA'], 'Mammoth': RU_BY_CODE['UTA'],
})

def ru_name(value, code=None):
    if code and code in RU_BY_CODE:
        return RU_BY_CODE[code]
    return RU_ALIASES.get(value, value)

def msk_time(value):
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(MSK).strftime("%d.%m.%Y в %H:%M МСК")
    except (ValueError, TypeError, AttributeError):
        return "время уточняется"
STATE_FILE = pathlib.Path('data/state.json')
SPORTS = ('NHL', 'KHL')
MIN_LEAD_HOURS = 18
FORECAST_HOURS = 168  # discover games one week ahead; never publish inside 18 hours
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; ICEEDGE/2.1)', 'Accept': 'application/json'}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def rate(wins, losses, ot=0):
    n = wins + losses + ot
    return (wins + 0.5 * ot + 2) / (n + 4) if n >= 5 else None


def nhl_events(date):
    data = fetch(f'https://api-web.nhle.com/v1/score/{date.isoformat()}')
    standings = fetch(f'https://api-web.nhle.com/v1/standings/{date.isoformat()}')
    records = {}
    for t in standings.get('standings', []):
        code = t.get('teamAbbrev', {}).get('default')
        if code:
            records[code] = rate(t.get('wins', 0), t.get('losses', 0), t.get('otLosses', 0))
    events = []
    for g in data.get('games', []):
        home, away = g.get('homeTeam', {}), g.get('awayTeam', {})
        hcode, acode = home.get('abbrev'), away.get('abbrev')
        state = g.get('gameState')
        events.append({
            'id': str(g['id']), 'sport': 'NHL', 'date': g.get('startTimeUTC'),
            'home': ru_name(home.get('name', {}).get('default', hcode or 'Home'), hcode),
            'away': ru_name(away.get('name', {}).get('default', acode or 'Away'), acode),
            'home_id': hcode, 'away_id': acode,
            'home_rate': records.get(hcode), 'away_rate': records.get(acode),
            'status': 'final' if state in ('OFF', 'FINAL') else 'pre' if state in ('FUT', 'PRE') else 'live',
            'home_score': home.get('score'), 'away_score': away.get('score'),
        })
    return events


def nba_events(date):
    # This endpoint contains NBA's *current* scoreboard only, not historical dates.
    data = fetch('https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json')
    board = data.get('scoreboard', {})
    board_date = board.get('gameDate', '')[:10]
    if board_date != date.isoformat():
        raise RuntimeError(f'NBA scoreboard date {board_date!r} != requested {date.isoformat()} (historical results unavailable)')
    events = []
    for g in board.get('games', []):
        home, away = g.get('homeTeam', {}), g.get('awayTeam', {})
        def record(t):
            try:
                return rate(int(t['wins']), int(t['losses']))
            except (KeyError, TypeError, ValueError):
                return None
        status = g.get('gameStatus')
        events.append({
            'id': str(g['gameId']), 'sport': 'NBA', 'date': g.get('gameTimeUTC'),
            'home': home.get('teamName', 'Home'), 'away': away.get('teamName', 'Away'),
            'home_id': str(home.get('teamId')), 'away_id': str(away.get('teamId')),
            'home_rate': record(home), 'away_rate': record(away),
            'status': 'final' if status == 3 else 'pre' if status == 1 else 'live',
            'home_score': home.get('score'), 'away_score': away.get('score'),
        })
    return events


def events_for(sport, date):
    if sport == 'NHL':
        return nhl_events(date)
    if sport == 'KHL':
        return khl_events(date)
    return []


_khl_schedule_cache = None

def khl_events(date):
    """Fetch KHL fixtures once per bot run; never fabricate absent events."""
    global _khl_schedule_cache
    if _khl_schedule_cache is None:
        # An API failure is logged as an ERROR by main(), not a misleading 0 games.
        _khl_schedule_cache = fetch_khl_schedule(dt.datetime.now(UTC).date(), days=9)
        print(f'KHL API: received {len(_khl_schedule_cache)} normalized upcoming fixtures')
        if not _khl_schedule_cache:
            print('WARNING: KHL API returned zero fixtures; check API response and season')
    return [x for x in _khl_schedule_cache if dt.datetime.fromisoformat(x['date']).date() == date]


def send(text):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat:
        raise RuntimeError('Missing Telegram credentials')
    body = urllib.parse.urlencode({'chat_id': chat, 'text': text}).encode()
    req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=body)
    with urllib.request.urlopen(req, timeout=25) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError('Telegram message failed')


# ICE EDGE — cinematic artwork, dynamic panels and real team crests.
# The approved artwork is used as the actual visual background (not redrawn).
CARD_W, CARD_H = 1374, 1145
ASSETS = pathlib.Path(__file__).resolve().parent / 'assets'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REG = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
TEAM_CODES = {v: k for k, v in RU_BY_CODE.items()}


def font(size, bold=True):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


def centered(d, txt, x, y, size, width=1200, fill='white', bold=True, stroke=1):
    txt = str(txt)
    while size > 17 and d.textbbox((0, 0), txt, font=font(size, bold))[2] > width:
        size -= 2
    d.text((x, y), txt, anchor='mm', font=font(size, bold), fill=fill,
           stroke_width=stroke, stroke_fill='#03101f')


def overlay(im, xy, color='#02cfff', opacity=244, radius=22, border=3):
    lay = Image.new('RGBA', im.size)
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle(xy, radius=radius, fill=(3, 13, 30, opacity), outline=color, width=border)
    im.alpha_composite(lay)


def glow(im, xy, color=(0, 175, 255), radius=18):
    glow_layer = Image.new('RGBA', im.size)
    d = ImageDraw.Draw(glow_layer)
    d.rounded_rectangle(xy, radius=radius, outline=(*color, 170), width=8)
    im.alpha_composite(glow_layer.filter(ImageFilter.GaussianBlur(14)))


def team_code(name):
    if name in RU_BY_CODE:
        return name
    return TEAM_CODES.get(ru_name(name))


def team_logo(name):
    code = team_code(name)
    if not code:
        return None
    local = ASSETS / 'logos' / (code + '.png')
    if local.exists():
        try:
            return Image.open(local).convert('RGBA')
        except OSError:
            local.unlink(missing_ok=True)
    # NHL logo first, ESPN PNG second. Cache successful downloads.
    urls = [f'https://a.espncdn.com/i/teamlogos/nhl/500/{code.lower()}.png',
            f'https://assets.nhle.com/logos/nhl/svg/{code}_light.svg']
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as r:
                content = r.read(1500000)
            if url.endswith('.svg'):
                import cairosvg
                content = cairosvg.svg2png(bytestring=content, output_width=500, output_height=500)
            logo = Image.open(io.BytesIO(content)).convert('RGBA')
            local.parent.mkdir(parents=True, exist_ok=True)
            logo.save(local)
            return logo
        except Exception as exc:
            print(f'Logo source failed {code}: {type(exc).__name__}')
    return None


def place_logo(im, name, x, y):
    logo = team_logo(name)
    if logo:
        logo.thumbnail((300, 285), Image.Resampling.LANCZOS)
        im.alpha_composite(logo, (int(x-logo.width/2), int(y-logo.height/2)))
    else:
        d = ImageDraw.Draw(im)
        centered(d, team_code(name) or 'НХЛ', x, y, 93, 290, '#ffffff')


def card(kind, home='', away='', pick='', when='', score='', wins=0, losses=0, pushes=0, edge=0.0):
    source = ASSETS / 'arena.png'
    if not source.exists():
        raise FileNotFoundError('Upload assets/arena.png from the provided ZIP')
    im = Image.open(source).convert('RGBA').resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
    # Preserve the approved arena's architecture, lights, ice and ICE EDGE header.
    # Cover baked-in example content so that no old match information remains.
    # Keep the approved ICE EDGE header and the ice-arena artwork.
    accent = {'win':'#00efab', 'loss':'#ff4765', 'push':'#f9c94c'}.get(kind, '#03d4ff')
    overlay(im, (960, 35, 1348, 182), '#42bdf5', 247, 15)
    d = ImageDraw.Draw(im)
    if when:
        datepart = when.split(' в ')[0]
        timepart = when.split(' в ')[-1]
        centered(d, datepart, 1154, 92, 42, 355)
        centered(d, timepart, 1154, 144, 35, 355, '#31d6ff')
    else:
        centered(d, 'НХЛ • ICE EDGE', 1154, 113, 32, 360, '#3ed8ff')
    # Content zones follow the approved poster's VS/crest/name/prediction composition.
    overlay(im, (28, 225, 1346, 739), '#125fa7', 250, 24)
    overlay(im, (47, 761, 1327, 976), accent, 252, 23, 4)
    glow(im, (47, 761, 1327, 976), (0, 160, 255) if kind=='forecast' else ((0,240,140) if kind=='win' else (255,65,95)))
    d = ImageDraw.Draw(im)
    if kind == 'stats':
        centered(d, 'СТАТИСТИКА КАНАЛА', 687, 284, 54, 1180)
        total = wins+losses
        pct = f'{wins/total*100:.0f}%' if total else '—'
        centered(d, pct, 687, 480, 185, 1000, '#30efb1')
        centered(d, 'ПРОХОДИМОСТЬ БЕЗ ВОЗВРАТОВ', 687, 594, 35, 1130, '#92dfff')
        centered(d, f'ПОБЕДЫ  {wins}      ПОРАЖЕНИЯ  {losses}      ВОЗВРАТЫ  {pushes}', 687, 833, 45, 1170)
        centered(d, 'ТОЛЬКО ОПУБЛИКОВАННЫЕ ПРОГНОЗЫ', 687, 915, 28, 1150, '#7edbff')
    else:
        heading = {'forecast':'ПРОГНОЗ НХЛ', 'win':'ПРОГНОЗ СЫГРАЛ!',
                   'loss':'ПРОГНОЗ НЕ СЫГРАЛ', 'push':'ВОЗВРАТ'}.get(kind,'НХЛ')
        centered(d, heading, 687, 278, 46, 1150, accent)
        place_logo(im, home, 322, 468)
        place_logo(im, away, 1052, 468)
        d = ImageDraw.Draw(im)
        centered(d, 'VS' if kind == 'forecast' else score, 687, 475,
                 132 if kind == 'forecast' else 95, 360)
        overlay(im, (75, 630, 614, 716), '#047de1', 247, 13)
        overlay(im, (760, 630, 1299, 716), '#047de1', 247, 13)
        d = ImageDraw.Draw(im)
        centered(d, ru_name(home).upper(), 344, 674, 48, 510)
        centered(d, ru_name(away).upper(), 1030, 674, 48, 510)
        if kind == 'forecast':
            centered(d, 'ПРОГНОЗ:', 687, 800, 33, 900, '#24cfff')
            centered(d, 'ПОБЕДА ' + ru_name(pick).upper(), 687, 867, 65, 1200)
            if edge >= 0.20:
                overlay(im, (470, 980, 904, 1030), '#21dda6', 244, 14, 2)
                d = ImageDraw.Draw(im)
                centered(d, '★ ПОВЫШЕННЫЙ ОТБОР', 687, 1005, 27, 410, '#d7fff4')
        else:
            centered(d, 'ИТОГ МАТЧА  ' + score, 687, 801, 33, 1150, accent)
            centered(d, 'ПРОГНОЗ: ПОБЕДА ' + ru_name(pick).upper(), 687, 868, 57, 1210)
        centered(d, 'С УЧЁТОМ ОВЕРТАЙМА И БУЛЛИТОВ', 687, 932, 27, 1100, '#4bd8ff')
    # Preserve the lower ice and puck in the approved artwork.
    overlay(im, (20, 1045, 640, 1118), '#1680bb', 214, 13, 2)
    d = ImageDraw.Draw(im)
    centered(d, '18+  •  СТАВКИ РИСКОВАННЫ. ГАРАНТИЙ НЕТ', 327, 1082, 22, 595)
    out = io.BytesIO()
    im.convert('RGB').save(out, format='PNG', optimize=True)
    return out.getvalue()

def send_photo(image, caption):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat:
        raise RuntimeError('Missing Telegram credentials')
    boundary = 'ICEEDGEBOUNDARY2'
    def part(name, value):
        return (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode('utf-8')
    payload = part('chat_id', chat) + part('caption', caption)
    payload += (f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="ice-edge.png"\r\nContent-Type: image/png\r\n\r\n').encode()
    payload += image + f'\r\n--{boundary}--\r\n'.encode()
    req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendPhoto', data=payload,
                                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(req, timeout=35) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError('Telegram photo failed')
    return result.get('result', {})

def load():
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        if isinstance(state.get('predictions'), dict):
            return state
    return {'predictions': {}}


def save(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')



def checkpoint_state(state):
    """Persist each Telegram acknowledgement to the remote repo during Actions.

    If remote persistence fails, stop rather than continue publishing more picks
    from a state that later runs might not see.
    """
    save(state)
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        return
    commands = [
        ['git', 'add', '--', str(STATE_FILE)],
        ['git', '-c', 'user.name=github-actions[bot]',
         '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
         'commit', '-m', 'Checkpoint ICE EDGE Telegram publications'],
        ['git', 'push', 'origin', 'HEAD'],
    ]
    subprocess.run(commands[0], check=True)
    staged = subprocess.run(['git', 'diff', '--cached', '--quiet'], check=False)
    if staged.returncode == 0:
        return
    if staged.returncode != 1:
        raise RuntimeError('Cannot inspect state checkpoint')
    subprocess.run(commands[1], check=True)
    subprocess.run(commands[2], check=True)


def export_prime(state):
    for p in state['predictions'].values():
        if p.get('sport') == 'NHL' and p.get('pick') and not p.get('market_type'):
            p['market_type'] = 'winner'
            p['market_label'] = 'Победа ' + p['pick'] + ' (включая ОТ и буллиты)'
        p.setdefault('probability', None)
        p.setdefault('totals', [])
    feed = {
        'updated_at': dt.datetime.now(UTC).isoformat(),
        'predictions': sorted(state['predictions'].values(),
                              key=lambda p: p.get('date', ''), reverse=True)
    }
    pathlib.Path('data/predictions.json').write_text(
        json.dumps(feed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    today = dt.datetime.now(UTC).date()
    state = load()
    # Legacy records have no Telegram message ID. Keep their history, but do not
    # count them as independently verifiable in the new channel statistics.
    for prior in state['predictions'].values():
        if 'publication_verified' not in prior:
            prior['publication_verified'] = bool(prior.get('forecast_message_id') and prior.get('forecast_published_at'))
            prior['legacy_record'] = not prior['publication_verified']
    save(state)
    errors = []
    fetched = {}
    pending = [p for p in state['predictions'].values() if p.get('status') == 'pending']
    # NHL scoreboard dates are league-local; fetch surrounding days.
    dates = {('NHL', today + dt.timedelta(days=offset)) for offset in range(-1, 9)}
    dates.update({(sport, today + dt.timedelta(days=offset)) for sport in ('KHL',) for offset in range(0, 8)})
    for p in pending:
        if p['sport'] == 'NHL':
            try:
                day = dt.datetime.fromisoformat(p['date'].replace('Z', '+00:00')).date()
                if 0 <= (today - day).days <= 7:
                    for offset in (-1, 0, 1):
                        dates.add(('NHL', day + dt.timedelta(days=offset)))
            except (TypeError, ValueError, KeyError):
                pass
    for sport, day in sorted(dates):
        try:
            fetched[(sport, day)] = events_for(sport, day)
            print(f'{sport} {day}: {len(fetched[(sport, day)])} games')
        except Exception as exc:
            errors.append(f'{sport} {day}: {exc}')
            print(f'ERROR {sport} {day}: {exc}')
    settled_count = 0
    # Send first, then persist the settlement immediately. A failed Telegram request
    # does not mark the pick as published; reruns will safely retry it.
    candidates = {g['id']: g for (league, _), games in fetched.items() if league == 'NHL' for g in games}
    for p in pending:
        match = candidates.get(p.get('event_id'))
        if not match or match.get('status') != 'final':
            continue
        try:
            hs, aws = int(match['home_score']), int(match['away_score'])
        except (ValueError, TypeError):
            continue
        # NHL games cannot finish tied, but handle incomplete or corrupted data safely.
        if hs == aws:
            continue
        winner = match['home_id'] if hs > aws else match['away_id']
        result = 'win' if winner == p.get('pick_id') else 'loss'
        score = f'{hs} : {aws}'
        # PRIME: settle directly from NHL final result, no Telegram dependency.
        p['result_published_at'] = dt.datetime.now(UTC).isoformat()
        p['result'] = result
        p['status'] = 'settled'
        p['final_score'] = score
        p['settled_at'] = dt.datetime.now(UTC).isoformat()
        state['predictions'][p['id']] = p
        checkpoint_state(state)
        settled_count += 1
    proposals = []
    now = dt.datetime.now(UTC)
    diagnostics = Counter()
    rejection_examples = []

    def reject(reason, game, details=''):
        diagnostics[reason] += 1
        if len(rejection_examples) < 30:
            name = f"{game.get('away', '?')} — {game.get('home', '?')}"
            suffix = f" | {details}" if details else ''
            rejection_examples.append(f"  SKIP [{reason}] {name} (id={game.get('id', '?')}){suffix}")

    for sport in SPORTS:
        if sport != 'NHL':
            print(f'{sport}: fixture discovery active; publishing disabled until validated sport-specific model is connected')
            continue
        # Deduplicate games appearing on overlapping scoreboard dates.
        seen = set()
        for g in (event for (league, _), games in fetched.items() if league == sport for event in games):
            if g['id'] in seen:
                continue
            seen.add(g['id'])
            diagnostics['unique_games'] += 1
            if g['status'] != 'pre':
                reject('not_upcoming', g, f"status={g['status']}")
                continue
            if g['home_rate'] is None or g['away_rate'] is None:
                reject('missing_team_form', g,
                       f"home_rate={g['home_rate']}, away_rate={g['away_rate']} (requires >=5 season games per team)")
                continue
            try:
                start = dt.datetime.fromisoformat(g['date'].replace('Z', '+00:00'))
                if start.tzinfo is None:
                    reject('invalid_start_time', g, 'missing timezone')
                    continue
                if start < now + dt.timedelta(hours=MIN_LEAD_HOURS):
                    reject('less_than_18h', g, f"start={start.isoformat()}")
                    continue
                if start > now + dt.timedelta(hours=FORECAST_HOURS):
                    reject('outside_discovery_window', g, f"start={start.isoformat()}")
                    continue
            except (TypeError, ValueError, AttributeError):
                reject('invalid_start_time', g, f"date={g.get('date')!r}")
                continue
            edge = g['home_rate'] - g['away_rate'] + 0.045
            if abs(edge) < 0.09:
                reject('edge_below_threshold', g, f"edge={edge:+.3f}, threshold=0.090")
                continue
            chosen_home = edge > 0
            key = f'{sport}:{g["id"]}'
            if key in state['predictions']:
                reject('already_in_state', g, f"key={key}")
                continue
            diagnostics['eligible'] += 1
            proposals.append({'id': key, 'event_id': g['id'], 'sport': sport,
                              'date': g['date'], 'home': g['home'], 'away': g['away'],
                              'pick': g['home'] if chosen_home else g['away'],
                              'pick_id': g['home_id'] if chosen_home else g['away_id'],
                              'edge': round(abs(edge), 3), 'home_rate': g['home_rate'],
                              'away_rate': g['away_rate'], 'status': 'pending', 'result': None,
                              'market_type': 'winner', 'market_label': 'Победа '+(g['home'] if chosen_home else g['away'])+' (включая ОТ и буллиты)',
                              'probability': None, 'totals': []})
    print('=== ICE EDGE selection diagnostics ===')
    print(f"Unique games reviewed: {diagnostics['unique_games']}")
    for reason in ('not_upcoming', 'missing_team_form', 'less_than_18h', 'outside_discovery_window',
                   'invalid_start_time', 'edge_below_threshold', 'already_in_state', 'eligible'):
        print(f'  {reason}: {diagnostics[reason]}')
    for item in rejection_examples:
        print(item)
    if diagnostics['unique_games'] == 0:
        print('WARNING: No games received from the NHL data source')
    if diagnostics['eligible'] == 0:
        print('INFO: No new forecasts qualify under the current rules; nothing will be posted')
    proposals.sort(key=lambda p: p['edge'], reverse=True)
    # PRIME 1.8: old edge proposals are SHADOW candidates only, never published.
    # Validate winner model on completed CURRENT-season games first.
    selected = []
    winner_history = []
    winner_approved = False
    winner_metrics = {'reason': 'history_unavailable'}
    try:
        _, winner_history = history(fetch, today)
        winner_approved, winner_metrics = validate_winners(winner_history)
        print(f'Winner model 1.8: approved={winner_approved}, metrics={winner_metrics}')
        if winner_approved:
            for old in proposals:
                # Existing candidates provide team IDs and match time; winner
                # model independently chooses the side (not the old edge).
                m = next((g for g in candidates.values() if str(g['id']) == str(old['event_id'])), None)
                if m is None:
                    continue
                decision = winner_pick(winner_history, m['home_id'], m['away_id'])
                if not decision or decision['probability'] < MIN_CONFIDENCE:
                    continue
                chosen_home = decision['pick_home']
                new = dict(old)
                new['pick'] = m['home'] if chosen_home else m['away']
                new['pick_id'] = m['home_id'] if chosen_home else m['away_id']
                new['market_label'] = 'Победа ' + new['pick'] + ' (включая ОТ и буллиты)'
                new['probability'] = decision['probability']
                new['probability_method'] = decision['method']
                new['selection_note'] = 'Проверенная на предыдущих матчах модель; исход не гарантирован'
                selected.append(new)
        print(f'Winner shadow: old_edge_candidates={len(proposals)}, eligible_to_publish={len(selected)}')
    except Exception as exc:
        print('WARNING: Winner validation unavailable; no new winner picks:', exc)
    new_count = 0
    for p in selected:
        # Recheck immediately before writing: never publish within 18h.
        kickoff = dt.datetime.fromisoformat(p['date'].replace('Z', '+00:00'))
        if kickoff - dt.datetime.now(UTC) < dt.timedelta(hours=MIN_LEAD_HOURS):
            print('SKIP late publication:', p['id'])
            continue
        # PRIME: publication means persisted in the app data feed.
        p['publication_verified'] = True
        p['forecast_published_at'] = dt.datetime.now(UTC).isoformat()
        p['publication_channel'] = 'prime'
        state['predictions'][p['id']] = p
        checkpoint_state(state)
        new_count += 1
    try:
        previous, current = [], winner_history if winner_history else history(fetch, today)[1]
        approved, metrics = validate(previous, current)
        added = enrich(state['predictions'], previous, current, approved)
        # Select one highest estimated probability among historically validated
        # totals per game. The winner model has no calibrated probability, so
        # do not falsely compare its edge score with a probability.
        for pred in state['predictions'].values():
            options = pred.get('totals') or []
            if pred.get('status') != 'pending' or not options:
                continue
            best = max(options, key=lambda x: x.get('probability', 0))
            pred['best_validated_total'] = best
            pred['selection_note'] = ('Лучший из прошедших историческую проверку тоталов; '
                                      'не сравнивается с вероятностью победы команды')
        print(f'Totals model 1.7: previous={len(previous)}, current={len(current)}, validated_lines={approved}, metrics={metrics}, published={added}')
    except Exception as exc:
        print('WARNING: Totals model unavailable:', exc)
    save(state)
    export_prime(state)
    print(f'Window: {MIN_LEAD_HOURS}h to {FORECAST_HOURS}h ahead. Candidates: {len(proposals)}')
    print(f'Done. New: {new_count}. Settled: {settled_count}. Total: {len(state["predictions"])}')
    if errors:
        print('WARNING: Partial data source failures: ' + '; '.join(errors))


if __name__ == '__main__':
    main()
