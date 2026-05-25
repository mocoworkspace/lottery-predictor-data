import json
import os
import re
import urllib.request
from datetime import datetime, timezone

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False
    print('Warning: requests/beautifulsoup4 not available, skipping Wikipedia scraping')

# ── 設定 ──────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get('API_KEY', '')
BASE_URL = 'https://v3.football.api-sports.io'
LEAGUE_ID = 98  # J1 League
current_year = datetime.now(timezone.utc).year

# api-football / Wikipedia の英語チーム名 → アプリ内の日本語チーム名
TEAM_NAME_JP = {
    'Kashima Antlers':            '鹿島アントラーズ',
    'Urawa Red Diamonds':         '浦和レッズ',
    'Urawa Reds':                 '浦和レッズ',
    'Gamba Osaka':                'ガンバ大阪',
    'Cerezo Osaka':               'セレッソ大阪',
    'Kawasaki Frontale':          '川崎フロンターレ',
    'Yokohama F.Marinos':         '横浜F・マリノス',
    'Yokohama F. Marinos':        '横浜F・マリノス',
    'Yokohama Marinos':           '横浜F・マリノス',
    'FC Tokyo':                   'FC東京',
    'Sanfrecce Hiroshima':        'サンフレッチェ広島',
    'Nagoya Grampus':             '名古屋グランパス',
    'Vissel Kobe':                'ヴィッセル神戸',
    'Sagan Tosu':                 'サガン鳥栖',
    'Kashiwa Reysol':             '柏レイソル',
    'Jubilo Iwata':               'ジュビロ磐田',
    'Júbilo Iwata':               'ジュビロ磐田',
    'Albirex Niigata':            'アルビレックス新潟',
    'Shonan Bellmare':            '湘南ベルマーレ',
    'FC Machida Zelvia':          'FC町田ゼルビア',
    'Machida Zelvia':             'FC町田ゼルビア',
    'Kyoto Sanga FC':             '京都サンガ',
    'Kyoto Sanga':                '京都サンガ',
    'Tokyo Verdy':                '東京ヴェルディ',
    'Avispa Fukuoka':             'アビスパ福岡',
    'Consadole Sapporo':          '北海道コンサドーレ札幌',
    'Hokkaido Consadole Sapporo': '北海道コンサドーレ札幌',
    'Vegalta Sendai':             'ベガルタ仙台',
    'Shimizu S-Pulse':            '清水エスパルス',
    'Montedio Yamagata':          'モンテディオ山形',
    'Omiya Ardija':               '大宮アルディージャ',
    'V-Varen Nagasaki':           'V・ファーレン長崎',
    'Tokushima Vortis':           '徳島ヴォルティス',
    'Fagiano Okayama':            'ファジアーノ岡山',
    'Renofa Yamaguchi':           'レノファ山口',
    'Blaublitz Akita':            'ブラウブリッツ秋田',
    'Thespakusatsu Gunma':        'ザスパクサツ群馬',
    'FC Imabari':                 'FC今治',
    'Roasso Kumamoto':            'ロアッソ熊本',
}


def resolve_team_name(raw: str) -> str:
    """英語チーム名を日本語アプリ名に変換。マッピングがなければそのまま返す。"""
    s = raw.strip()
    if s in TEAM_NAME_JP:
        return TEAM_NAME_JP[s]
    sl = s.lower()
    for eng, jp in TEAM_NAME_JP.items():
        if eng.lower() == sl:
            return jp
    for eng, jp in TEAM_NAME_JP.items():
        if sl in eng.lower() or eng.lower() in sl:
            return jp
    return s


def apifootball_fetch(path: str) -> dict:
    """api-football.com からデータを取得（APIキー未設定の場合は空を返す）。"""
    if not API_KEY:
        return {}
    try:
        req = urllib.request.Request(
            f'{BASE_URL}{path}',
            headers={'x-apisports-key': API_KEY}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f'  -> api-football error: {e}')
        return {}


# ── 1. 試合日程（api-football, 取得できない場合は空）────────────────────────
print('=== Fixtures (api-football) ===')
SEASON = current_year
fixtures = []
standings = []

if API_KEY:
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    future_month = min(datetime.now(timezone.utc).month + 2, 12)
    future_str = datetime.now(timezone.utc).replace(month=future_month).strftime('%Y-%m-%d')

    for year in [current_year, current_year - 1]:
        print(f'Fetching J1 fixtures for season {year}...')
        data = apifootball_fetch(f'/fixtures?league={LEAGUE_ID}&season={year}&next=13')
        fixtures = data.get('response', [])
        print(f'  -> next=13: {len(fixtures)} fixtures')
        if not fixtures:
            data = apifootball_fetch(
                f'/fixtures?league={LEAGUE_ID}&season={year}&from={today_str}&to={future_str}'
            )
            fixtures = data.get('response', [])
            print(f'  -> date range: {len(fixtures)} fixtures')
        if fixtures:
            SEASON = year
            break

    if fixtures:
        print('Fetching standings...')
        standings_data = apifootball_fetch(f'/standings?league={LEAGUE_ID}&season={SEASON}')
        standings = standings_data.get('response', [])
        print(f'  -> {len(standings)} standings entries')
    else:
        print('Note: No fixtures found via api-football (J1 may not be on free plan)')
else:
    print('Note: API_KEY not set, skipping api-football')

fixtures_output = {
    'updated_at': datetime.now(timezone.utc).isoformat(),
    'season': SEASON,
    'fixtures': fixtures,
    'standings': standings,
}
with open('fixtures.json', 'w', encoding='utf-8') as f:
    json.dump(fixtures_output, f, ensure_ascii=False, indent=2)
print(f'fixtures.json updated (fixtures={len(fixtures)}, standings={len(standings)}).\n')


# ── 2. 過去の試合結果（Wikipedia スクレイピング）────────────────────────────
print('=== Historical Data (Wikipedia CC-BY-SA) ===')


def scrape_wikipedia_j1(year: int):
    """
    Wikipedia の J1 League ページから結果クロステーブルをスクレイピングし、
    チームごとのホーム/アウェイ勝率データを返す。

    Source: Wikipedia (CC-BY-SA)
    https://en.wikipedia.org/wiki/{year}_J1_League
    """
    url = f'https://en.wikipedia.org/wiki/{year}_J1_League'
    hdrs = {
        'User-Agent': (
            'LotteryPredictorApp/1.0 '
            '(https://github.com/mocoworkspace/lottery-predictor-data; '
            'open-source personal project)'
        )
    }
    print(f'Fetching {url} ...')
    try:
        resp = requests.get(url, headers=hdrs, timeout=30)
        if resp.status_code == 404:
            print('  -> 404 Not Found')
            return None, {}
        resp.raise_for_status()
    except Exception as e:
        print(f'  -> Error fetching: {e}')
        return None, {}

    if ('Wikipedia does not have an article' in resp.text
            or 'Wikipedia does not yet have an article' in resp.text):
        print('  -> Page does not exist')
        return None, {}

    soup = BeautifulSoup(resp.text, 'lxml')
    h1 = soup.find('h1', {'id': 'firstHeading'})
    print(f'  -> Title: {h1.get_text(strip=True) if h1 else "(not found)"}')

    all_tables = soup.find_all('table', class_=lambda c: c and 'wikitable' in c)
    print(f'  -> {len(all_tables)} wikitable(s) found')

    # 結果クロステーブルを探す:
    # J1 は 18 チームなので 18 行以上、かつスコアパターンを含むテーブルを選択
    results_table = None
    for table in all_tables:
        rows_all = table.find_all('tr')
        if len(rows_all) < 12:
            continue
        # 最初の数行にスコアパターン ("2–1" など) があるかチェック
        has_scores = False
        for row in rows_all[1:6]:
            for cell in row.find_all('td'):
                if re.search(r'\d\s*[–—\-]\s*\d', cell.get_text()):
                    has_scores = True
                    break
            if has_scores:
                break
        if has_scores:
            results_table = table
            print(f'  -> Found results table ({len(rows_all)} rows)')
            break

    if results_table is None:
        print('  -> No results cross-table found on this page')
        return None, {}

    rows_all = results_table.find_all('tr')

    # ── First pass: 行ヘッダーからチームリストを構築 ──────────────────────
    # 各行の最初のセルにはチームのフルネーム（Wikipedia リンク付き）が入っている
    team_list = []
    for row in rows_all[1:]:  # 先頭行（列ヘッダー）はスキップ
        cells = row.find_all(['th', 'td'])
        if not cells:
            continue
        first = cells[0]
        link = first.find('a')
        raw = link.get_text(strip=True) if link else first.get_text(strip=True)
        raw = raw.strip()
        # ラベル文字や数字のみの行は除外
        if not raw or len(raw) < 2 or re.match(r'^[↓\\↑→←\s\d]+$', raw):
            continue
        team_jp = resolve_team_name(raw)
        team_list.append(team_jp)

    print(f'  -> Team list ({len(team_list)}): {team_list[:5]}...')

    if len(team_list) < 10:
        print('  -> Too few teams extracted from row headers')
        return None, {}

    # ── Second pass: スコアを解析 ──────────────────────────────────────────
    # クロステーブルの構造:
    #   cells[0]        = ホームチーム名（行ヘッダー）
    #   cells[j+1]      = アウェイチーム j との対戦スコア（j=0..N-1）
    #   対角線 (home==away) はスコアなし（セルは存在する）
    team_stats = {
        t: {'home_games': 0, 'home_wins': 0, 'away_games': 0, 'away_wins': 0}
        for t in team_list
    }
    match_count = 0

    for i, row in enumerate(rows_all[1:]):
        if i >= len(team_list):
            break
        home_jp = team_list[i]
        cells = row.find_all(['th', 'td'])

        for j, away_jp in enumerate(team_list):
            if home_jp == away_jp:
                continue  # 対角線（同一チーム）はスキップ
            cell_idx = j + 1  # cells[0] は行ヘッダー
            if cell_idx >= len(cells):
                continue
            cell = cells[cell_idx]
            score_text = cell.get_text(strip=True)
            # 脚注 [1] などを除去
            score_text = re.sub(r'\[.*?\]', '', score_text).strip()

            # スコアパターン: "2–1", "0-0", "3—2" など
            m = re.search(r'(\d+)\s*[–—\-]\s*(\d+)', score_text)
            if m:
                hs, as_ = int(m.group(1)), int(m.group(2))
                team_stats[home_jp]['home_games'] += 1
                team_stats[away_jp]['away_games'] += 1
                if hs > as_:
                    team_stats[home_jp]['home_wins'] += 1
                elif as_ > hs:
                    team_stats[away_jp]['away_wins'] += 1
                match_count += 1

    # 試合数が少なすぎるチームは除外（取得途中のシーズンデータの混入対策）
    team_stats = {
        k: v for k, v in team_stats.items()
        if v['home_games'] + v['away_games'] >= 5
    }

    if match_count == 0:
        print('  -> No scores parsed (season may not have results yet)')
        return None, {}

    print(f'  -> Success: {match_count} matches, {len(team_stats)} teams')
    return year, team_stats


historical_season = None
team_stats = {}

MIN_MATCHES_CURRENT = 100   # 進行中シーズンを採用する最低試合数（約5節相当）
MIN_MATCHES_PREVIOUS = 200  # 前年データを採用する最低試合数

if SCRAPING_AVAILABLE:
    # 今シーズン → 前年 → 前々年 の順に試みる
    for hist_year in [current_year, current_year - 1, current_year - 2]:
        historical_season, team_stats = scrape_wikipedia_j1(hist_year)
        if not team_stats:
            continue
        total_matches = sum(v['home_games'] for v in team_stats.values())
        threshold = MIN_MATCHES_CURRENT if hist_year == current_year else MIN_MATCHES_PREVIOUS
        if total_matches >= threshold:
            print(f'Using J1 {historical_season} data '
                  f'({total_matches} matches, {len(team_stats)} teams).')
            break
        else:
            print(f'J1 {hist_year}: only {total_matches} matches '
                  f'(need {threshold}), trying previous year...')
            team_stats = {}
    if not team_stats:
        print('Warning: Could not retrieve historical data from Wikipedia.')
else:
    print('Skipping Wikipedia scraping (requests/bs4 not installed).')

# 勝率を追加
for stats in team_stats.values():
    hg = max(stats['home_games'], 1)
    ag = max(stats['away_games'], 1)
    stats['home_win_rate'] = round(stats['home_wins'] / hg, 4)
    stats['away_win_rate'] = round(stats['away_wins'] / ag, 4)

historical_output = {
    'updated_at': datetime.now(timezone.utc).isoformat(),
    'season': historical_season,
    'match_count': sum(v['home_games'] for v in team_stats.values()),
    'team_stats': team_stats,
    'source': 'Wikipedia (CC-BY-SA) https://en.wikipedia.org/wiki/J1_League',
}
with open('historical.json', 'w', encoding='utf-8') as f:
    json.dump(historical_output, f, ensure_ascii=False, indent=2)
print(f'historical.json updated: season={historical_season}, {len(team_stats)} teams.')
