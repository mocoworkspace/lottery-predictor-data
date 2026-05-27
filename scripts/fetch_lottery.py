"""
Fetch real lottery draw results from loto-life.net.

CSV sources (loto6 / loto7 / miniloto):
  Loto 6   : https://loto-life.net/csv/loto6
  Loto 7   : https://loto-life.net/csv/loto7
  Mini Loto: https://loto-life.net/csv/mini

HTML sources (bingo5 / numbers3 / numbers4):
  BINGO5   : https://loto-life.net/bingo5
  Numbers3 : https://loto-life.net/numbers3
  Numbers4 : https://loto-life.net/numbers4
  ※ Latest draw only (no bulk CSV available)

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

# ── HTML タイプ (bingo5 / numbers3 / numbers4) ────────────────────────────────
HTML_SOURCES = {
    'bingo5':   'https://loto-life.net/bingo5',
    'numbers3': 'https://loto-life.net/numbers3',
    'numbers4': 'https://loto-life.net/numbers4',
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


def parse_latest_draw_from_html(lottery_id: str, html: str) -> dict | None:
    """
    HTML から最新1件の抽せん結果をパースして返す。失敗時は None を返す。

    【HTML 構造（共通）】
      <tr><td>回別</td>   <td colspan="N">第XXXX回</td></tr>
      <tr><td>抽選日</td> <td colspan="N">YYYY年MM月DD日</td></tr>

    【BINGO5】
      <table class="bingo-table"><tr><td>4</td>...<td>FREE</td>...</tr>...</table>
      ※ FREE セルは \d+ にマッチしないため自動スキップ

    【numbers3 / numbers4】
      <tr><td>当選番号</td><td colspan="N">667</td></tr>
      → 1桁ずつ分解: [6, 6, 7]
    """
    # 回号
    m = re.search(r'回別</td>\s*<td[^>]*>第(\d+)回</td>', html)
    if not m:
        return None
    round_num = int(m.group(1))

    # 抽選日
    m = re.search(
        r'抽選日</td>\s*<td[^>]*>(\d{4})年(\d{1,2})月(\d{1,2})日</td>', html
    )
    if not m:
        return None
    date_str = f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'

    # 数字
    if lottery_id in ('numbers3', 'numbers4'):
        m = re.search(r'当選番号</td>\s*<td[^>]*>(\d+)</td>', html)
        if not m:
            return None
        numbers = [int(d) for d in m.group(1)]
    elif lottery_id == 'bingo5':
        m = re.search(r'class="bingo-table">(.*?)</table>', html, re.DOTALL)
        if not m:
            return None
        numbers = sorted(int(n) for n in re.findall(r'<td>(\d+)</td>', m.group(1)))
    else:
        return None

    if not numbers:
        return None

    return {'round': round_num, 'date': date_str, 'numbers': numbers}


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

# ── HTML タイプ (bingo5 / numbers3 / numbers4) ────────────────────────────────
for lottery_id, url in HTML_SOURCES.items():
    print(f'\n[{lottery_id}] (HTML)')

    html_text = fetch_html_http(url)
    if html_text is not None:
        time.sleep(DELAY_SEC)

    prev_draws = existing.get(lottery_id, [])

    if html_text is not None:
        draw = parse_latest_draw_from_html(lottery_id, html_text)
        if draw:
            prev_rounds = {d['round'] for d in prev_draws}
            new_latest  = draw['round']
            print(f'  -> Latest: round {new_latest}, {draw["date"]}')
            if new_latest not in prev_rounds:
                # 新着データを先頭に追加してソート
                merged = [draw] + [d for d in prev_draws if d['round'] != new_latest]
                merged.sort(key=lambda d: d['round'], reverse=True)
                output[lottery_id] = merged[:MAX_DRAWS]
                any_updated = True
                print(f'  -> New draw added.')
            else:
                output[lottery_id] = prev_draws
                print(f'  -> Already up to date.')
            success_count += 1
        else:
            print('  -> Parse failed (HTML format may have changed)')
            output[lottery_id] = prev_draws
    else:
        count = len(prev_draws)
        print(f'  -> Using existing data ({count} draws)')
        output[lottery_id] = prev_draws

# ── lottery.json を書き出す ────────────────────────────────────────────────────
if any_updated or not os.path.exists('lottery.json'):
    with open('lottery.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\nlottery.json updated: {success_count}/{len(CSV_SOURCES) + len(HTML_SOURCES)} sources OK.')
else:
    # 新規抽せんなし → タイムスタンプのみ更新
    existing['updated_at'] = output['updated_at']
    with open('lottery.json', 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f'\nlottery.json: no new draws found, timestamp updated.')
