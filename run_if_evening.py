#!/usr/bin/env python3
"""
デスクトップへのログオン時にタスクスケジューラから呼ばれる入り口スクリプト。
rakuten_threads_bot/run_if_evening.py と同じパターン。

- 19時より前なら何もせず終了する
- その日すでに実行済みなら何もせず終了する(同じ晩に何度もログオンしても1日1回だけ)
- 上記に該当しなければ generate_and_publish.py を1回実行する(記事1本を生成・公開)

実行結果は site_log.txt に追記される(generate_and_publish.py 側のログと共通)。
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
MARKER_FILE = BASE_DIR / "last_auto_run_date.txt"
LOG_FILE = BASE_DIR / "site_log.txt"

POSTS_PER_RUN = 2
INTERVAL_SECONDS = 120  # 連続実行の間隔(APIへの負荷を分散するため)


def log(message: str):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def already_run_today(today: str) -> bool:
    if MARKER_FILE.exists():
        return MARKER_FILE.read_text(encoding="utf-8").strip() == today
    return False


def mark_run_today(today: str):
    MARKER_FILE.write_text(today, encoding="utf-8")


def main():
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    if now.hour < 19:
        log(f"19時より前({now.strftime('%H:%M')})なので今回は実行しません。")
        return

    if already_run_today(today):
        log("本日はすでに実行済みなのでスキップします。")
        return

    log(f"19時以降のログオンを検知。generate_and_publish.py を{POSTS_PER_RUN}回連続実行します。")

    success_count = 0
    for i in range(POSTS_PER_RUN):
        log(f"--- {i + 1}/{POSTS_PER_RUN}件目 ---")
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "generate_and_publish.py")],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
        )
        if result.stdout:
            log(result.stdout.strip())
        if result.stderr:
            log(f"[stderr] {result.stderr.strip()}")

        if result.returncode == 0:
            success_count += 1
        else:
            log(f"この回はエラー終了しました(code={result.returncode})。次の回に進みます。")

        if i < POSTS_PER_RUN - 1:
            time.sleep(INTERVAL_SECONDS)

    mark_run_today(today)
    log(f"完了。{success_count}/{POSTS_PER_RUN}件の記事を公開しました。本日分は使用済みにしています。")


if __name__ == "__main__":
    main()
