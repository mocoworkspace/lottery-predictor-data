"""
Fetch real lottery draw results from Mizuho Bank public CSV files.

Sources (public data, no login required):
  Loto 6   : https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto6/csv/loto6.csv
  Loto 7   : https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto7/csv/loto7.csv
  Mini Loto: https://www.mizuhobank.co.jp/retail/takarakuji/loto/miniloto/csv/miniloto.csv

Lottery numbers are public information (government-operated lottery).
"""

import json
import re
import time
from datetime import datetime, timezone

import requests

# ── 設定 ──────────────────────────────────────────────────────────────────────
MAX_DRAWS = 200   # 各宝くじの取得件数上限（最新から）
DELAY_SEC = 1.5   # リクエスト間の待機秒数

SOURCES = {
    'loto6': {
        'url': 'https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto6/csv/loto6.csv',
        'num_count': 6,
    },
    'loto7': {
        'url': 'https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto7/csv/loto7.csv',
        'num_count': 7,
    },
    'miniloto': {
        'url': 'https://www.mizuhobank.co.jp/retail/takarakuji/loto/miniloto/csv/miniloto.csv',
        'num_count': 5,
    },
}

HEADERS = {
    'User-Agent': (
        'LotteryPredictorApp/1.0 '
        '(https://github.com/mocoworkspace/lottery-predictor-data; '
        'open-source personal project)'
    )
}


def fetch_csv(url: str) -> str | None:
    """CSV を取得してテキストで返す（CP932 / UTF-8 を自動判定）。"""
    print(f'  Fetching {url} ...')
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f'  -> Error: {e}')
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

        # カンマまたはタブ区切りで分割、余計な引用符を除去
        parts = [p.strip().strip('"').strip() for p in re.split(r'[,\t]', line)]

        # 先頭が正の整数 → データ行
        if not (parts and re.fullmatch(r'\d+', parts[0])):
            continue

        try:
            round_num = int(parts[0])

            # 日付: YYYY/MM/DD または YYYY-MM-DD
            date_str = parts[1]
            try:
                draw_date = datetime.strptime(date_str, '%Y/%m/%d')
            except ValueError:
                draw_date = datetime.strptime(date_str, '%Y-%m-%d')

            # 本数字（列2〜2+num_count-1）
            numbers = sorted(int(parts[2 + i]) for i in range(num_count))

            # ボーナス数字（列 2+num_count）
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

    # 新しい順に並べ、MAX_DRAWS 件に絞る
    draws.sort(key=lambda d: d['round'], reverse=True)
    return draws[:MAX_DRAWS]


# ── メイン処理 ─────────────────────────────────────────────────────────────────
print('=== Lottery Data (Mizuho Bank) ===')

output = {'updated_at': datetime.now(timezone.utc).isoformat()}
success_count = 0

for lottery_id, cfg in SOURCES.items():
    print(f'\n[{lottery_id}]')
    csv_text = fetch_csv(cfg['url'])

    if csv_text is None:
        print(f'  -> Skipped (fetch failed)')
        output[lottery_id] = []
    else:
        draws = parse_draws(csv_text, cfg['num_count'])
        output[lottery_id] = draws
        if draws:
            print(f'  -> {len(draws)} draws parsed '
                  f'(latest: round {draws[0]["round"]}, {draws[0]["date"]})')
            success_count += 1
        else:
            print(f'  -> No draws parsed (CSV format may have changed)')

    # リクエスト間に待機
    time.sleep(DELAY_SEC)

with open('lottery.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f'\nlottery.json updated: {success_count}/{len(SOURCES)} sources OK.')
