"""
Fetch real lottery draw results from loto-life.net.

Sources (public data, updated ~19:45 JST on each draw day):
  Loto 6   : https://loto-life.net/csv/loto6
  Loto 7   : https://loto-life.net/csv/loto7
  Mini Loto: https://loto-life.net/csv/mini

Column layout (loto-life.net CSV):
  [0] round, [1] date (YYYY-MM-DD),
  loto6   : [2-7] numbers (6),  [8]  bonus
  loto7   : [2-8] numbers (7),  [9]  bonus (first of two)
  miniloto: [2-6] numbers (5),  [7]  bonus, [8] set-ball (ignored)

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

SOURCES = {
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

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/csv,text/plain,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
}


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

    先頭列が整数のみの行をデータ行とみなし、
    ヘッダー行や空行を自動スキップする。
    """
    draws = []
    for raw_line in csv_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if not (parts and re.fullmatch(r'\d+', parts[0])):
            continue   # ヘッダー・注釈行をスキップ
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

for lottery_id, cfg in SOURCES.items():
    print(f'\n[{lottery_id}]')

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
        # フェッチ失敗 → 既存データを維持
        count = len(existing.get(lottery_id, []))
        print(f'  -> Using existing data ({count} draws)')
        output[lottery_id] = existing.get(lottery_id, [])

# lottery.json を書き出す
if any_updated or not os.path.exists('lottery.json'):
    with open('lottery.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\nlottery.json updated: {success_count}/{len(SOURCES)} sources OK.')
else:
    # 新規抽せんなし → タイムスタンプのみ更新
    existing['updated_at'] = output['updated_at']
    with open('lottery.json', 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f'\nlottery.json: no new draws found, timestamp updated.')
