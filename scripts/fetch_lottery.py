"""
Fetch real lottery draw results from loto-life.net.

CSV sources (loto6 / loto7 / miniloto):
  Loto 6   : https://loto-life.net/csv/loto6
  Loto 7   : https://loto-life.net/csv/loto7
  Mini Loto: https://loto-life.net/csv/mini

HTML sources (bingo5 / numbers3 / numbers4):
  BINGO5   : https://loto-life.net/bingo5        (latest 1 draw only)
  Numbers3 : https://loto-life.net/numbers3/past (latest 15 draws)
  Numbers4 : https://loto-life.net/numbers4/past (latest 15 draws)

Lottery numbers are public information (government-operated lottery).
"""

import json
import os
import re
import time
from datetime import datetime, timezone

import requests

# ── 設定 ──────────────────────────────────────────────────────────────────────
MAX_DRAWS = 200   # 各宝くじの取得件数上限（最新から）
DELAY_SEC = 1.0   # HTTPリクエスト間の待機秒数

# ── CSV タイプ (loto6 / loto7 / miniloto) ─────────────────────────────────────
CSV_SOURCES = {
    'loto6': {
        'url':       'https://loto-life.net/csv/loto6',
        'num_start': 2,
        'num_end':   8,   # exclusive → indices 2..7  (6 numbers)
        'bonus_idx': 8,
    },
    'loto7': {
        'url':       'https://loto-life.net/csv/loto7',
        'num_start': 2,
        'num_end':   9,   # exclusive → indices 2..8  (7 numbers)
        'bonus_idx': 9,   # first of two bonus balls
    },
    'miniloto': {
        'url':       'https://loto-life.net/csv/mini',
        'num_start': 2,
        'num_end':   7,   # exclusive → indices 2..6  (5 numbers)
        'bonus_idx': 7,
    },
}

# ── HTML タイプ latest (bingo5) ───────────────────────────────────────────────
BINGO5_URL = 'https://loto-life.net/bingo5'

# ── HTML タイプ /past ページ (numbers3 / numbers4) ────────────────────────────
# /past ページは最新15件を一覧表示するため、取りこぼしを防げる
PAST_SOURCES = {
    'numbers3': 'https://loto-life.net/numbers3/past',
    'numbers4': 'https://loto-life.net/numbers4/past',
}

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,text/csv,text/plain,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
}


# ── CSV フェッチ・パース ───────────────────────────────────────────────────────

def fetch_csv_http(url: str) -> str | None:
    """HTTP で CSV を取得する。"""
    print(f'  Fetching {url} ...')
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f'  -> HTTP fetch failed: {e}')
        return None
    for enc in ('utf-8-sig', 'utf-8', 'cp932'):
        try:
            return resp.content.decode(enc)
        except UnicodeDecodeError:
            continue
    return resp.content.decode('utf-8', errors='replace')


def parse_draws(csv_text: str, num_start: int, num_end: int, bonus_idx: int) -> list[dict]:
    """
    CSV テキストから抽せん結果を解析する。
    先頭列が整数のみの行をデータ行とみなし、ヘッダー行や空行を自動スキップする。
    """
    draws = []
    for raw_line in csv_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if not (parts and re.fullmatch(r'\d+', parts[0])):
            continue
        try:
            round_num = int(parts[0])
            draw_date = datetime.strptime(parts[1], '%Y-%m-%d')
            numbers   = sorted(int(parts[i]) for i in range(num_start, num_end))
            bonus     = (int(parts[bonus_idx])
                         if bonus_idx < len(parts) and parts[bonus_idx].isdigit()
                         else None)
            draws.append({
                'round':   round_num,
                'date':    draw_date.strftime('%Y-%m-%d'),
                'numbers': numbers,
                'bonus':   bonus,
            })
        except (ValueError, IndexError):
            continue
    draws.sort(key=lambda d: d['round'], reverse=True)
    return draws[:MAX_DRAWS]


# ── HTML フェッチ・パース ──────────────────────────────────────────────────────

def fetch_html_http(url: str) -> str | None:
    """HTML ページを取得する。"""
    print(f'  Fetching {url} ...')
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f'  -> HTTP fetch failed: {e}')
        return None
    for enc in ('utf-8', 'utf-8-sig', 'cp932'):
        try:
            return resp.content.decode(enc)
        except UnicodeDecodeError:
            continue
    return resp.content.decode('utf-8', errors='replace')


def parse_latest_bingo5(html: str) -> dict | None:
    """
    BINGO5 メインページから最新1件をパースする。

    【HTML 構造】
      <tr><td>回別</td>   <td colspan="N">第XXXX回</td></tr>
      <tr><td>抽選日</td> <td colspan="N">YYYY年MM月DD日</td></tr>
      <table class="bingo-table"><tr><td>4</td>...<td>FREE</td>...</tr>...</table>
      ※ FREE セルは \d+ にマッチしないため自動スキップ
    """
    m = re.search(r'回別</td>\s*<td[^>]*>第(\d+)回</td>', html)
    if not m:
        return None
    round_num = int(m.group(1))

    m = re.search(
        r'抽選日</td>\s*<td[^>]*>(\d{4})年(\d{1,2})月(\d{1,2})日</td>', html
    )
    if not m:
        return None
    date_str = f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'

    m = re.search(r'class="bingo-table">(.*?)</table>', html, re.DOTALL)
    if not m:
        return None
    numbers = sorted(int(n) for n in re.findall(r'<td>(\d+)</td>', m.group(1)))
    if not numbers:
        return None

    return {'round': round_num, 'date': date_str, 'numbers': numbers}


def parse_past_draws_numbers(html: str) -> list[dict]:
    """
    numbers3 / numbers4 の /past ページから複数件をパースする。

    【HTML 構造】
      <th colspan="8">第XXXX回(YYYY年MM月DD日) の抽選結果</th>
      ...
      <th>当選番号</th>
      <td colspan="7">NNN</td>

    → 各回の「第XXXX回(YYYY年MM月DD日)」と直後の「当選番号 ... NNN」を対応付ける。
    """
    pattern = (
        r'第(\d+)回\((\d{4})年(\d{1,2})月(\d{1,2})日\)'
        r'.*?当選番号\s*</th>\s*<td[^>]*>\s*(\d+)'
    )
    draws = []
    for m in re.finditer(pattern, html, re.DOTALL):
        round_num = int(m.group(1))
        date_str  = f'{m.group(2)}-{int(m.group(3)):02d}-{int(m.group(4)):02d}'
        numbers   = [int(d) for d in m.group(5)]
        draws.append({'round': round_num, 'date': date_str, 'numbers': numbers})
    draws.sort(key=lambda d: d['round'], reverse=True)
    return draws


# ── メイン処理 ─────────────────────────────────────────────────────────────────
print('=== Lottery Data Updater ===')

# 既存の lottery.json を読み込む（存在すれば）
existing: dict = {}
if os.path.exists('lottery.json'):
    try:
        with open('lottery.json', 'r', encoding='utf-8') as f:
            existing = json.load(f)
        print('Loaded existing lottery.json')
    except Exception as e:
        print(f'Could not read existing lottery.json: {e}')

output: dict  = {'updated_at': datetime.now(timezone.utc).isoformat()}
success_count = 0
any_updated   = False

# ── CSV タイプ (loto6 / loto7 / miniloto) ─────────────────────────────────────
for lottery_id, cfg in CSV_SOURCES.items():
    print(f'\n[{lottery_id}] (CSV)')

    csv_text = fetch_csv_http(cfg['url'])
    if csv_text is not None:
        time.sleep(DELAY_SEC)

    if csv_text is not None:
        draws = parse_draws(csv_text, cfg['num_start'], cfg['num_end'], cfg['bonus_idx'])
        if draws:
            output[lottery_id] = draws
            prev_draws  = existing.get(lottery_id, [])
            prev_latest = prev_draws[0]['round'] if prev_draws else None
            new_latest  = draws[0]['round']
            print(f'  -> {len(draws)} draws parsed '
                  f'(latest: round {new_latest}, {draws[0]["date"]})')
            if new_latest != prev_latest:
                any_updated = True
            success_count += 1
        else:
            print('  -> No draws parsed (CSV format may have changed)')
            output[lottery_id] = existing.get(lottery_id, [])
    else:
        count = len(existing.get(lottery_id, []))
        print(f'  -> Using existing data ({count} draws)')
        output[lottery_id] = existing.get(lottery_id, [])

# ── HTML タイプ: BINGO5 (latest 1 draw) ──────────────────────────────────────
print(f'\n[bingo5] (HTML latest-only)')
prev_draws = existing.get('bingo5', [])
html_text  = fetch_html_http(BINGO5_URL)
if html_text is not None:
    time.sleep(DELAY_SEC)
    draw = parse_latest_bingo5(html_text)
    if draw:
        prev_rounds = {d['round'] for d in prev_draws}
        print(f'  -> Latest: round {draw["round"]}, {draw["date"]}')
        if draw['round'] not in prev_rounds:
            merged = [draw] + [d for d in prev_draws if d['round'] != draw['round']]
            merged.sort(key=lambda d: d['round'], reverse=True)
            output['bingo5'] = merged[:MAX_DRAWS]
            any_updated = True
            print('  -> New draw added.')
        else:
            output['bingo5'] = prev_draws
            print('  -> Already up to date.')
        success_count += 1
    else:
        print('  -> Parse failed (HTML format may have changed)')
        output['bingo5'] = prev_draws
else:
    print(f'  -> Using existing data ({len(prev_draws)} draws)')
    output['bingo5'] = prev_draws

# ── HTML タイプ: numbers3 / numbers4 (/past ページから15件取得) ────────────────
for lottery_id, past_url in PAST_SOURCES.items():
    print(f'\n[{lottery_id}] (HTML /past)')
    prev_draws  = existing.get(lottery_id, [])
    prev_rounds = {d['round'] for d in prev_draws}

    past_html = fetch_html_http(past_url)
    if past_html is not None:
        time.sleep(DELAY_SEC)
        past_draws = parse_past_draws_numbers(past_html)
        new_draws  = [d for d in past_draws if d['round'] not in prev_rounds]
        if new_draws:
            rounds_added = [d['round'] for d in new_draws]
            print(f'  -> {len(new_draws)} new draw(s) added: rounds {rounds_added}')
            merged = new_draws + prev_draws
            merged.sort(key=lambda d: d['round'], reverse=True)
            output[lottery_id] = merged[:MAX_DRAWS]
            any_updated = True
        else:
            latest = past_draws[0]['round'] if past_draws else 'N/A'
            print(f'  -> Already up to date (latest: round {latest})')
            output[lottery_id] = prev_draws
        success_count += 1
    else:
        print('  -> /past fetch failed, using existing data')
        output[lottery_id] = prev_draws

# ── lottery.json を書き出す ────────────────────────────────────────────────────
if any_updated or not os.path.exists('lottery.json'):
    with open('lottery.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\nlottery.json updated: {success_count}/{len(CSV_SOURCES) + 1 + len(PAST_SOURCES)} sources OK.')
else:
    # 新規抽せんなし → タイムスタンプのみ更新
    existing['updated_at'] = output['updated_at']
    with open('lottery.json', 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f'\nlottery.json: no new draws found, timestamp updated.')
