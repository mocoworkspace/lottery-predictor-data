import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False
    print('Warning: requests/beautifulsoup4 not available, skipping Wikipedia scraping')

# ── スクレイピングポリシー ────────────────────────────────────────────────────
# Wikipedia の利用規約・robots.txt を遵守する。
# 週1回・最大3リクエストのみ。リクエスト間に待機時間を設ける。
SCRAPE_DELAY_SEC = 2      # リクエスト間の待機秒数
SCRAPE_MAX_RETRIES = 2    # 429/503 時のリトライ回数
SCRAPE_RETRY_WAIT = 10    # リトライ待機秒数

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
    # 2026年 百年構想リーグ 追加チーム
    'Mito HollyHock':             '水戸ホーリーホック',
    'JEF United Chiba':           'ジェフユナイテッド千葉',
    'JEF United':                 'ジェフユナイテッド千葉',
    'JEF United Ichihara Chiba':  'ジェフユナイテッド千葉',
}


def resolve_team_name(raw: str) -> str:
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


# ── 年ごとのWikipedia URL ──────────────────────────────────────────────────────
# J1は2026年から秋春制に移行。2026年は移行措置として「百年構想リーグ」を開催。
SPECIAL_WIKIPEDIA_URLS = {
    2026: 'https://en.wikipedia.org/wiki/J1_100_Year_Vision_League',
}


def get_wikipedia_url(year: int) -> str:
    return SPECIAL_WIKIPEDIA_URLS.get(year,
                                      'https://en.wikipedia.org/wiki/{}_J1_League'.format(year))


def apifootball_fetch(path: str) -> dict:
    if not API_KEY:
        return {}
    try:
        req = urllib.request.Request(
            '{}{}'.format(BASE_URL, path),
            headers={'x-apisports-key': API_KEY}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print('  -> api-football error: {}'.format(e))
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
        print('Fetching J1 fixtures for season {}...'.format(year))
        data = apifootball_fetch('/fixtures?league={}&season={}&next=13'.format(LEAGUE_ID, year))
        fixtures = data.get('response', [])
        print('  -> next=13: {} fixtures'.format(len(fixtures)))
        if not fixtures:
            data = apifootball_fetch(
                '/fixtures?league={}&season={}&from={}&to={}'.format(
                    LEAGUE_ID, year, today_str, future_str)
            )
            fixtures = data.get('response', [])
            print('  -> date range: {} fixtures'.format(len(fixtures)))
        if fixtures:
            SEASON = year
            break

    if fixtures:
        print('Fetching standings...')
        standings_data = apifootball_fetch('/standings?league={}&season={}'.format(LEAGUE_ID, SEASON))
        standings = standings_data.get('response', [])
        print('  -> {} standings entries'.format(len(standings)))
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
print('fixtures.json updated (fixtures={}, standings={}).\n'.format(len(fixtures), len(standings)))


# ── 2. 過去の試合結果（Wikipedia スクレイピング）────────────────────────────
print('=== Historical Data (Wikipedia CC-BY-SA) ===')


_last_request_time = 0.0


def _polite_get(url, hdrs):
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < SCRAPE_DELAY_SEC:
        wait = SCRAPE_DELAY_SEC - elapsed
        print('  -> Waiting {:.1f}s (rate limit)...'.format(wait))
        time.sleep(wait)

    for attempt in range(1, SCRAPE_MAX_RETRIES + 2):
        try:
            _last_request_time = time.time()
            resp = requests.get(url, headers=hdrs, timeout=30)
            if resp.status_code in (429, 503):
                print('  -> HTTP {}, waiting {}s before retry (attempt {}/{})...'.format(
                    resp.status_code, SCRAPE_RETRY_WAIT, attempt, SCRAPE_MAX_RETRIES + 1))
                time.sleep(SCRAPE_RETRY_WAIT)
                continue
            return resp
        except requests.RequestException as e:
            print('  -> Request error (attempt {}): {}'.format(attempt, e))
            if attempt <= SCRAPE_MAX_RETRIES:
                time.sleep(SCRAPE_RETRY_WAIT)
    return None


def _parse_results_table(table):
    """
    結果クロステーブル1枚をパースしてチームリスト・試合記録・試合数を返す。
    Returns: (team_list, match_records, match_count)
    """
    rows_all = table.find_all('tr')

    # First pass: 行ヘッダーからチームリストを構築
    team_list = []
    for row in rows_all[1:]:
        cells = row.find_all(['th', 'td'])
        if not cells:
            continue
        first = cells[0]
        link = first.find('a')
        raw = (link.get_text(strip=True) if link else first.get_text(strip=True)).strip()
        if not raw or len(raw) < 2 or re.match(r'^[downarrow\\uparrow\s\d]+$', raw):
            continue
        team_list.append(resolve_team_name(raw))

    if len(team_list) < 5:
        return [], [], 0

    # Second pass: スコアを解析
    match_records = []
    match_count = 0

    for i, row in enumerate(rows_all[1:]):
        if i >= len(team_list):
            break
        home_jp = team_list[i]
        cells = row.find_all(['th', 'td'])

        for j, away_jp in enumerate(team_list):
            if home_jp == away_jp:
                continue
            cell_idx = j + 1
            if cell_idx >= len(cells):
                continue
            score_text = re.sub(r'\[.*?\]', '',
                                cells[cell_idx].get_text(strip=True)).strip()
            m = re.search(r'(\d+)\s*[–—\-]\s*(\d+)', score_text)
            if m:
                hs, as_ = int(m.group(1)), int(m.group(2))
                match_records.append({
                    'home': home_jp,
                    'away': away_jp,
                    'home_score': hs,
                    'away_score': as_,
                })
                match_count += 1

    return team_list, match_records, match_count


def scrape_wikipedia_j1(year):
    """
    Wikipedia の J1 League ページから結果クロステーブルをスクレイピングし、
    チームごとのホーム/アウェイ勝率データを返す。

    東西分割など複数テーブルがある場合（2026年 百年構想リーグ等）はすべてマージする。

    スクレイピングポリシー:
    - 週1回・最大3リクエストのみ実行（GitHub Actions の cron による）
    - リクエスト間に待機時間を設け、サーバー負荷を最小化
    - Wikipedia の robots.txt および利用規約を遵守
    - Source: Wikipedia (CC-BY-SA)
    """
    url = get_wikipedia_url(year)
    hdrs = {
        'User-Agent': (
            'LotteryPredictorApp/1.0 '
            '(https://github.com/mocoworkspace/lottery-predictor-data; '
            'open-source personal project; weekly data update only)'
        )
    }
    print('Fetching {} ...'.format(url))
    resp = _polite_get(url, hdrs)
    if resp is None:
        print('  -> Failed after retries')
        return None, {}, []
    if resp.status_code == 404:
        print('  -> 404 Not Found')
        return None, {}, []
    try:
        resp.raise_for_status()
    except Exception as e:
        print('  -> HTTP error: {}'.format(e))
        return None, {}, []

    if ('Wikipedia does not have an article' in resp.text
            or 'Wikipedia does not yet have an article' in resp.text):
        print('  -> Page does not exist')
        return None, {}, []

    soup = BeautifulSoup(resp.text, 'lxml')
    h1 = soup.find('h1', {'id': 'firstHeading'})
    print('  -> Title: {}'.format(h1.get_text(strip=True) if h1 else '(not found)'))

    all_tables = soup.find_all('table', class_=lambda c: c and 'wikitable' in c)
    print('  -> {} wikitable(s) found'.format(len(all_tables)))

    # 結果クロステーブルをすべて収集（東西分割など複数テーブルに対応）
    results_tables = []
    for table in all_tables:
        rows = table.find_all('tr')
        if len(rows) < 8:
            continue
        has_scores = any(
            re.search(r'\d\s*[–—\-]\s*\d', cell.get_text())
            for row in rows[1:6]
            for cell in row.find_all('td')
        )
        if has_scores:
            results_tables.append(table)

    if not results_tables:
        print('  -> No results cross-table found on this page')
        return None, {}, []

    print('  -> Found {} results table(s)'.format(len(results_tables)))

    # 全テーブルをパースしてマージ
    team_stats = {}
    all_match_records = []
    total_match_count = 0

    for table in results_tables:
        team_list, match_records, match_count = _parse_results_table(table)
        if not team_list:
            continue

        print('     Table: {} teams, {} matches'.format(len(team_list), match_count))

        for t in team_list:
            if t not in team_stats:
                team_stats[t] = {
                    'home_games': 0, 'home_wins': 0,
                    'away_games': 0, 'away_wins': 0,
                }

        for rec in match_records:
            home_jp = rec['home']
            away_jp = rec['away']
            hs = rec['home_score']
            as_ = rec['away_score']
            team_stats[home_jp]['home_games'] += 1
            team_stats[away_jp]['away_games'] += 1
            if hs > as_:
                team_stats[home_jp]['home_wins'] += 1
            elif as_ > hs:
                team_stats[away_jp]['away_wins'] += 1

        all_match_records.extend(match_records)
        total_match_count += match_count

    # 試合数が少なすぎるチームは除外
    team_stats = {
        k: v for k, v in team_stats.items()
        if v['home_games'] + v['away_games'] >= 5
    }

    if total_match_count == 0:
        print('  -> No scores parsed (season may not have results yet)')
        return None, {}, []

    print('  -> Success: {} matches, {} teams'.format(total_match_count, len(team_stats)))
    return year, team_stats, all_match_records


# ── 今年・去年の両シーズンを取得して seasons 配列に格納 ────────────────────
# フォールバックではなく、両年のデータを並存させる。
# MIN_MATCHES_FOR_INCLUDE 以上の試合データがあるシーズンのみ収録する。
MIN_MATCHES_FOR_INCLUDE = 30  # シーズンデータを含める最低試合数

seasons_list = []

if SCRAPING_AVAILABLE:
    for hist_year in [current_year, current_year - 1]:
        season_year, season_team_stats, season_match_records = scrape_wikipedia_j1(hist_year)
        if not season_team_stats:
            print('J1 {}: no data retrieved, skipping.'.format(hist_year))
            continue
        total_matches = sum(v['home_games'] for v in season_team_stats.values())
        if total_matches < MIN_MATCHES_FOR_INCLUDE:
            print('J1 {}: only {} matches (need {}), skipping.'.format(
                hist_year, total_matches, MIN_MATCHES_FOR_INCLUDE))
            continue
        # 勝率を計算して追加
        for stats in season_team_stats.values():
            hg = max(stats['home_games'], 1)
            ag = max(stats['away_games'], 1)
            stats['home_win_rate'] = round(stats['home_wins'] / hg, 4)
            stats['away_win_rate'] = round(stats['away_wins'] / ag, 4)
        seasons_list.append({
            'season': season_year,
            'match_count': len(season_match_records),
            'team_stats': season_team_stats,
            'matches': season_match_records,
        })
        print('Added J1 {} data ({} matches, {} teams).'.format(
            season_year, len(season_match_records), len(season_team_stats)))
    if not seasons_list:
        print('Warning: Could not retrieve historical data from Wikipedia.')
else:
    print('Skipping Wikipedia scraping (requests/bs4 not installed).')

historical_output = {
    'updated_at': datetime.now(timezone.utc).isoformat(),
    'seasons': seasons_list,
    'source': 'Wikipedia (CC-BY-SA) https://en.wikipedia.org/wiki/J1_League',
}
with open('historical.json', 'w', encoding='utf-8') as f:
    json.dump(historical_output, f, ensure_ascii=False, indent=2)

if seasons_list:
    print('historical.json updated: {} season(s).'.format(len(seasons_list)))
    for s in seasons_list:
        print('  season={}, {} teams, {} matches.'.format(
            s['season'], len(s['team_stats']), s['match_count']))
else:
    print('historical.json updated: no season data (empty).')
