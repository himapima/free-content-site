"""Gemini APIキーの多重化ヘルパー。

無料枠は「1日あたりのリクエスト数」がプロジェクト単位で決まっているため、
複数のボットが同じキーを同時に使うとすぐ 429 (RESOURCE_EXHAUSTED) になる。
.env に複数のキーを入れておき、429 が出たら次のキーへ自動で切り替える。

.env で読み込むキー名(上から順に使う):
    GEMINI_API_KEY / GEMINI_API_KEY_2〜5 / GEMINI_API_KEY_NOTE
"""

import os
import time

KEY_ENV_NAMES = (
    "GEMINI_API_KEY",
    "GEMINI_API_KEY_2",
    "GEMINI_API_KEY_3",
    "GEMINI_API_KEY_4",
    "GEMINI_API_KEY_5",
    "GEMINI_API_KEY_NOTE",
)

# 直前に成功したキーの位置。次回もそこから始めることで無駄な429を減らす。
_start_index = 0


def api_keys():
    """.env に設定されているキーを重複なしで順番に返す"""
    keys = []
    seen = set()
    for name in KEY_ENV_NAMES:
        key = (os.environ.get(name) or "").strip()
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def is_quota_error(err) -> bool:
    """無料枠の使い切り。別のAPIキーに切り替えれば直る"""
    msg = str(err)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg


def is_busy_error(err) -> bool:
    """Gemini側が混んでいるだけ。キーを変えても直らないので、待って同じキーで再試行する"""
    msg = str(err)
    return "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower()


def call_with_failover(call, rounds: int = 3, waits=(20, 40, 60)):
    """call(api_key) を実行する。

    - 429(無料枠切れ)  → 次のキーに切り替えてすぐ再試行
    - 503(Gemini混雑)  → キーを変えても直らないので、待ってから再試行
    - それ以外の例外   → そのまま呼び出し元へ投げる

    待って再試行するのは最大 rounds 周まで。
    """
    global _start_index

    keys = api_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY が設定されていません")

    last_error = None
    for round_no in range(rounds):
        for offset in range(len(keys)):
            index = (_start_index + offset) % len(keys)
            try:
                result = call(keys[index])
                _start_index = index  # 次回もこのキーから
                return result
            except Exception as e:  # noqa: BLE001 - 呼び出し元でまとめて扱う
                last_error = e
                if is_quota_error(e):
                    continue  # 枠切れ → 次のキーを試す
                if is_busy_error(e):
                    break  # 混雑 → キーを変えても無駄。待ってから再試行する
                raise
        # 枠切れ or 混雑。少し待ってからもう一周する。
        if round_no < rounds - 1:
            time.sleep(waits[min(round_no, len(waits) - 1)])

    raise RuntimeError(f"Gemini APIの呼び出しに失敗しました: {last_error}")


# ------------------------------------------------------------------
# 既存のリトライループにそのまま差し込める、カーソル方式のAPI
#   client = genai.Client(api_key=gemini_keys.current_key())
#   ... 429が出たら ...
#   if gemini_keys.switch_key():   # まだ試していないキーが残っている
#       continue                   # すぐ next のキーで再試行
#   else:
#       ...全キー枠切れ...
# ------------------------------------------------------------------

_cursor = 0
_tried = set()


def current_key() -> str:
    keys = api_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY が設定されていません")
    return keys[_cursor % len(keys)]


def key_label() -> str:
    """ログ用。キーの中身は出さず「何本目か」だけを表す"""
    keys = api_keys()
    return f"APIキー{(_cursor % max(len(keys), 1)) + 1}/{len(keys)}"


def switch_key() -> bool:
    """429が出たときに次のキーへ進む。まだ試していないキーが残っていればTrue"""
    global _cursor
    keys = api_keys()
    if not keys:
        return False
    _tried.add(_cursor % len(keys))
    _cursor += 1
    return (_cursor % len(keys)) not in _tried


def mark_success():
    """呼び出しが成功したら、枠切れ判定をリセットする"""
    _tried.clear()
