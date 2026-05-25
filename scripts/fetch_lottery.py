"""
Fetch real lottery draw results from Mizuho Bank public CSV files.

Sources (public data, no login required):
  Loto 6   : https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto6/csv/loto6.csv
  Loto 7   : https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto7/csv/loto7.csv
  Mini Loto: https://www.mizuhobank.co.jp/retail/takarakuji/loto/miniloto/csv/miniloto.csv

NOTE: Mizuho Bank uses Akamai CDN which blocks automated HTTP clients.
      This script first checks for manually-downloaded CSV files in the csv/ directory.
      If found, it parses them and updates lottery.json.
      If not found, it attempts an HTTP download (which may be blocked).

Manual update workflow:
  1. In your browser, download each CSV from the URLs above.
  2. Save them as  csv/loto6.csv, csv/loto7.csv, csv/miniloto.csv
  3. Run: python scripts/fetch_lottery.py
  4. Commit and push: git add lottery.json csv/ && git commit -m "Update lottery data"

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
DELAY_SEC = 1.5   # HTTPリクエスト間の待機秒数

SOURCES = {
    'loto6': {
        'url': 'https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto6/csv/loto6.csv',
        'local': 'csv/loto6.csv',
        'num_count': 6,
    },
    'loto7': {
        'url': 'https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto7/csv/loto7.csv',
        'local': 'csv/loto7.csv',
        'num_count': 7,
    },
    'miniloto': {
        'url': 'https://www.mizuhobank.co.jp/retail/takarakuji/loto/miniloto/csv/miniloto.csv',
        'local': 'csv/miniloto.csv',
        'num_count': 5,
    },
}

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
    'Connection': 'keep-alive',
}


def read_local_csv(path: str) -> str | None:
    """ローカルの CSV ファイルを読み込む（CP932 / UTF-8 を自動判定）。"""
    if not os.path.exists(path):
        return None
    print(f'  Reading local file: {path}')
    with open(path, 'rb') as f:
        raw = f.read()
    for enc in ('cp932', 'utf-8-sig', 'utf-8'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('cp932', errors='replace')


def fetch_csv_http(url: str) -> str | None:
    """HTTP で CSV を取得する（Akamai 保護サイトでは 403 になる場合あり）。"""
    parent_url = url.rsplit('/csv/', 1)[0] + '/'
    headers = {**HEADERS, 'Referer': parent_url,
               'Accept': 'text/csv,application/octet-stream,*/*;q=0.8'}
    print(f'  Fetching {url} ...')
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f'  -> HTTP fetch failed: {e}')
        return None
    for enc in ('cp932', 'utf-8-sig', 'utf-8'):
        try:
            return resp.content.decode(enc)
        except UnicodeDecodeError:
            continue
    return resp.content.decode('cp932', errors='replace')


def parse_draws(csv_text: str, num_count: int) -> list[dict]:
    """
    CSV テキストから抽せん結果を解析する。

    みずほ銀行 CSV の列構成（ロト6例）:
      第回, 抽せん日, 第1数字, ..., 第N数字, ボーナス数字, セット球, ...
    行の先頭が整数であればデータ行とみなす（ヘッダー・注釈行を自動スキップ）。
    """
    draws = []
    for raw_line in csv_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip().strip('"').strip() for p in re.split(r'[,\t]', line)]
        if not (parts and re.fullmatch(r'\d+', parts[0])):
            continue
        try:
            round_num = int(parts[0])
            date_str = parts[1]
            try:
                draw_date = datetime.strptime(date_str, '%Y/%m/%d')
            except ValueError:
                draw_date = datetime.strptime(date_str, '%Y-%m-%d')
            numbers = sorted(int(parts[2 + i]) for i in range(num_count))
            bonus_idx = 2 + num_count
            bonus = int(parts[bonus_idx]) if bonus_idx < len(parts) and parts[bonus_idx].isdigit() else None
            draws.append({
                'round': round_num,
                'date': draw_date.strftime('%Y-%m-%d'),
                'numbers': numbers,
                'bonus': bonus,
            })
        except (ValueError, IndexError):
            continue
    draws.sort(key=lambda d: d['round'], reverse=True)
    return draws[:MAX_DRAWS]


# ── メイン処理 ─────────────────────────────────────────────────────────────────
print('=== Lottery Data Updater ===')

# 既存の lottery.json を読み込む（存在すれば）
existing = {}
if os.path.exists('lottery.json'):
    try:
        with open('lottery.json', 'r', encoding='utf-8') as f:
            existing = json.load(f)
        print(f'Loaded existing lottery.json')
    except Exception as e:
        print(f'Could not read existing lottery.json: {e}')

output = {'updated_at': datetime.now(timezone.utc).isoformat()}
success_count = 0
any_updated = False

for lottery_id, cfg in SOURCES.items():
    print(f'\n[{lottery_id}]')
    csv_text = None

    # ① ローカルファイルを優先
    csv_text = read_local_csv(cfg['local'])

    # ② なければ HTTP ダウンロードを試みる
    if csv_text is None:
        csv_text = fetch_csv_http(cfg['url'])
        if csv_text is None:
            time.sleep(DELAY_SEC)

    if csv_text is not None:
        draws = parse_draws(csv_text, cfg['num_count'])
        if draws:
            output[lottery_id] = draws
            prev_count = len(existing.get(lottery_id, []))
            print(f'  -> {len(draws)} draws parsed '
                  f'(latest: round {draws[0]["round"]}, {draws[0]["date"]})')
            if len(draws) != prev_count:
                any_updated = True
            success_count += 1
        else:
            print(f'  -> No draws parsed (CSV format may have changed)')
            output[lottery_id] = existing.get(lottery_id, [])
    else:
        # フェッチ失敗 → 既存データを維持
        print(f'  -> Using existing data ({len(existing.get(lottery_id, []))} draws)')
        output[lottery_id] = existing.get(lottery_id, [])

# 変更があった場合のみ書き出し
if any_updated or not os.path.exists('lottery.json'):
    with open('lottery.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\nlottery.json updated: {success_count}/{len(SOURCES)} sources OK.')
else:
    # タイムスタンプだけ更新
    existing['updated_at'] = output['updated_at']
    with open('lottery.json', 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f'\nlottery.json: no new draws found, timestamp updated.')
