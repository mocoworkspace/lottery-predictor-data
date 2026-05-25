import json
import os
import urllib.request
from datetime import datetime, timezone

API_KEY = os.environ['API_KEY']
BASE_URL = 'https://v3.football.api-sports.io'
LEAGUE_ID = 98
SEASON = datetime.now().year  # 現在の年をシーズンとして使用

def fetch(path):
    req = urllib.request.Request(
        f'{BASE_URL}{path}',
        headers={'x-apisports-key': API_KEY}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

print(f'Fetching fixtures for J1 season {SEASON}...')
fixtures_data = fetch(f'/fixtures?league={LEAGUE_ID}&season={SEASON}&next=13')
fixtures = fixtures_data.get('response', [])
print(f'  -> {len(fixtures)} fixtures found')

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
