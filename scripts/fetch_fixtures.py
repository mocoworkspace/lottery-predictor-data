import json
import os
import urllib.request
from datetime import datetime, timezone

API_KEY = os.environ['API_KEY']
BASE_URL = 'https://v3.football.api-sports.io'
LEAGUE_ID = 98

# api-football.com の英語チーム名 → アプリ内の日本語チーム名
TEAM_NAME_JP = {
    'Kashima Antlers': '鹿島アントラーズ',
    'Urawa Red Diamonds': '浦和レッズ',
    'Gamba Osaka': 'ガンバ大阪',
    'Cerezo Osaka': 'セレッソ大阪',
    'Kawasaki Frontale': '川崎フロンターレ',
    'Yokohama F.Marinos': '横浜F・マリノス',
    'FC Tokyo': 'FC東京',
    'Sanfrecce Hiroshima': 'サンフレッチェ広島',
    'Nagoya Grampus': '名古屋グランパス',
    'Vissel Kobe': 'ヴィッセル神戸',
    'Sagan Tosu': 'サガン鳥栖',
    'Kashiwa Reysol': '柏レイソル',
    'Jubilo Iwata': 'ジュビロ磐田',
    'Albirex Niigata': 'アルビレックス新潟',
    'Shonan Bellmare': '湘南ベルマーレ',
    'FC Machida Zelvia': 'FC町田ゼルビア',
    'Kyoto Sanga FC': '京都サンガ',
    'Tokyo Verdy': '東京ヴェルディ',
}

def fetch(path):
    req = urllib.request.Request(
        f'{BASE_URL}{path}',
        headers={'x-apisports-key': API_KEY}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

# ── 1. 試合日程（upcoming fixtures）──────────────────────────
current_year = datetime.now().year
today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
future = datetime.now(timezone.utc).replace(
    month=min(datetime.now().month + 2, 12)
).strftime('%Y-%m-%d')

SEASON = None
fixtures = []
for year in [current_year, current_year - 1]:
    print(f'Fetching fixtures for J1 season {year}...')
    data = fetch(f'/fixtures?league={LEAGUE_ID}&season={year}&next=13')
    fixtures = data.get('response', [])
    print(f'  -> next=13: {len(fixtures)} fixtures found')
    if not fixtures:
        data = fetch(f'/fixtures?league={LEAGUE_ID}&season={year}&from={today}&to={future}')
        fixtures = data.get('response', [])
        print(f'  -> date range: {len(fixtures)} fixtures found')
    if fixtures:
        SEASON = year
        break

if SEASON is None:
    SEASON = current_year
    print('Warning: No upcoming fixtures found.')

print('Fetching standings...')
standings_data = fetch(f'/standings?league={LEAGUE_ID}&season={SEASON}')
standings = standings_data.get('response', [])
print(f'  -> {len(standings)} standings entries')

fixtures_output = {
    'updated_at': datetime.now(timezone.utc).isoformat(),
    'season': SEASON,
    'fixtures': fixtures,
    'standings': standings,
}
with open('fixtures.json', 'w', encoding='utf-8') as f:
    json.dump(fixtures_output, f, ensure_ascii=False, indent=2)
print('fixtures.json updated.')

# ── 2. 過去の試合結果（status=FT）────────────────────────────
historical_matches = []
historical_season = None
for year in [current_year, current_year - 1]:
    print(f'Fetching finished matches for J1 season {year}...')
    data = fetch(f'/fixtures?league={LEAGUE_ID}&season={year}&status=FT')
    matches = data.get('response', [])
    print(f'  -> {len(matches)} finished matches found')
    if matches:
        # チーム名サンプルを表示（デバッグ用）
        sample_names = set()
        for m in matches[:5]:
            sample_names.add(m['teams']['home']['name'])
            sample_names.add(m['teams']['away']['name'])
        print(f'  -> sample team names: {sample_names}')
        historical_matches = matches
        historical_season = year
        break

# チームごとの勝率を計算
team_stats = {}
unknown_teams = set()
for m in historical_matches:
    home_api = m['teams']['home']['name']
    away_api = m['teams']['away']['name']
    home_score = m['goals']['home']
    away_score = m['goals']['away']
    if home_score is None or away_score is None:
        continue

    home_jp = TEAM_NAME_JP.get(home_api, home_api)
    away_jp = TEAM_NAME_JP.get(away_api, away_api)
    if home_api not in TEAM_NAME_JP:
        unknown_teams.add(home_api)
    if away_api not in TEAM_NAME_JP:
        unknown_teams.add(away_api)

    for team in [home_jp, away_jp]:
        if team not in team_stats:
            team_stats[team] = {
                'home_games': 0, 'home_wins': 0,
                'away_games': 0, 'away_wins': 0,
            }

    team_stats[home_jp]['home_games'] += 1
    team_stats[away_jp]['away_games'] += 1
    if home_score > away_score:
        team_stats[home_jp]['home_wins'] += 1
    elif away_score > home_score:
        team_stats[away_jp]['away_wins'] += 1

# 勝率を追加
for stats in team_stats.values():
    hg = max(stats['home_games'], 1)
    ag = max(stats['away_games'], 1)
    stats['home_win_rate'] = round(stats['home_wins'] / hg, 4)
    stats['away_win_rate'] = round(stats['away_wins'] / ag, 4)

if unknown_teams:
    print(f'Warning: unmapped team names: {unknown_teams}')

historical_output = {
    'updated_at': datetime.now(timezone.utc).isoformat(),
    'season': historical_season,
    'match_count': len(historical_matches),
    'team_stats': team_stats,
}
with open('historical.json', 'w', encoding='utf-8') as f:
    json.dump(historical_output, f, ensure_ascii=False, indent=2)
print(f'historical.json updated: {len(historical_matches)} matches, {len(team_stats)} teams.')
