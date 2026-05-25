import json
import os
import urllib.request
from datetime import datetime, timezone

API_KEY = os.environ['API_KEY']
BASE_URL = 'https://v3.football.api-sports.io'
LEAGUE_ID = 98

def fetch(path):
    req = urllib.request.Request(
        f'{BASE_URL}{path}',
        headers={'x-apisports-key': API_KEY}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

# 現在年から順に試してデータがあるシーズンを使う
current_year = datetime.now().year
SEASON = None
fixtures = []
for year in [current_year, current_year - 1]:
    print(f'Fetching fixtures for J1 season {year}...')
    data = fetch(f'/fixtures?league={LEAGUE_ID}&season={year}&next=13')
    fixtures = data.get('response', [])
    print(f'  -> {len(fixtures)} fixtures found')
    if fixtures:
        SEASON = year
        break

if SEASON is None:
    SEASON = current_year
    print('Warning: No upcoming fixtures found for any season.')

print('Fetching standings...')
standings_data = fetch(f'/standings?league={LEAGUE_ID}&season={SEASON}')
standings = standings_data.get('response', [])
print(f'  -> standings fetched')

output = {
    'updated_at': datetime.now(timezone.utc).isoformat(),
    'season': SEASON,
    'fixtures': fixtures,
    'standings': standings,
}

with open('fixtures.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print('fixtures.json updated successfully.')
