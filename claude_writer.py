#!/usr/bin/env python3
"""
記事生成用のClaude Code CLI(ヘッドレス実行)呼び出しユーティリティ。

Gemini API(無料枠)ではなく、ユーザーのClaudeサブスクリプションを使う。
`claude setup-token` で発行した長期OAuthトークン(CLAUDE_CODE_OAUTH_TOKEN)で認証する
(2026-09-10、Geminiの無料枠が不安定なため「サブスクで課金しているこのClaude自身を使う」
方針にユーザーの指示で切り替えた)。

Gemini版(ai_writer.py)と違い、WebSearchツールを許可しているため実際にWeb検索してから
執筆できる。ユーザーから「ちゃんとリサーチしてから書く」ことを繰り返し求められているため、
情報系記事は必ずWebSearchを使わせる設計にしている。
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
CLAUDE_CLI_PATH = os.environ.get(
    "CLAUDE_CLI_PATH",
    r"C:\Users\naoya\tools\node\node-v24.21.0-win-x64\node_modules\@anthropic-ai\claude-code\bin\claude.exe",
)
CLAUDE_MODEL = os.environ.get("CLAUDE_WRITER_MODEL", "sonnet")
TIMEOUT_SECONDS = 300

ARTICLE_TONE_GUIDE = """\
文体・構成のルール:
- 丁寧で読みやすい「です・ます」調。断定しすぎず、根拠を示しながら説明する。
- 命令形(〜しろ、〜せよ)や乱暴なスラングは使わない。
- タイトルは検索されそうな具体的なキーワードを含み、30字程度にする。
- 見出し(H2)を3〜5個に分け、それぞれ200〜400字程度で説明する。
- 誇張・断定的な効能表現(「必ず」「絶対」など)は避ける。
- 【参考情報】に書かれている事実だけを根拠にし、書かれていない効果・スペック・
  数値は絶対に作り出さない。検索で調べた内容以外の事実(具体的な統計値等)を
  でっち上げない。
"""

ARTICLE_JSON_FORMAT = (
    '{"title": "記事タイトル", "meta_description": "120字程度の要約",'
    ' "intro": "導入文(150字程度)",'
    ' "sections": [{"heading": "見出し", "body": "本文"}, ...],'
    ' "conclusion": "まとめ(100字程度)"}'
)

PRODUCT_ARTICLE_JSON_FORMAT = (
    '{"title": "記事タイトル", "meta_description": "120字程度の要約",'
    ' "intro": "導入文(150字程度)",'
    ' "sections": [{"heading": "自然な短い見出し(商品名そのままではなく内容が伝わる見出し)",'
    ' "body": "本文", "product_index": 1}, ...],'
    ' "conclusion": "まとめ(100字程度)"}'
)


def _run_claude(prompt: str, allowed_tools: str = "") -> str:
    """claude CLIをヘッドレス実行(-p)し、テキスト応答を返す"""
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN が設定されていません(claude setup-tokenで発行)")
    if not Path(CLAUDE_CLI_PATH).exists():
        raise RuntimeError(f"claude CLIが見つかりません: {CLAUDE_CLI_PATH}")

    cmd = [CLAUDE_CLI_PATH, "-p", prompt, "--model", CLAUDE_MODEL, "--output-format", "json"]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLIの実行に失敗しました(code={result.returncode}): {result.stderr[:500]}")

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"claude CLIの出力をJSONとして解釈できませんでした: {e}\n{result.stdout[:500]}")

    if envelope.get("is_error"):
        raise RuntimeError(f"claude CLIがエラーを返しました: {envelope.get('result')}")

    return (envelope.get("result") or "").strip()


def _parse_json(text: str) -> dict:
    """```json ... ``` のコードフェンスを剥がしてJSONとして解釈する"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}


REQUIRED_KEYS = {"title", "meta_description", "intro", "sections", "conclusion"}


def _is_valid(article: dict) -> bool:
    if not REQUIRED_KEYS.issubset(article.keys()):
        return False
    if not article["title"] or not article["sections"]:
        return False
    return True


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _missing_names(article: dict, required_names: list[str]) -> list[str]:
    dumped = _normalize_ws(json.dumps(article, ensure_ascii=False))
    return [n for n in required_names if _normalize_ws(n) not in dumped]


def generate_info_article(genre_label: str, topic_hint: str, avoid_titles: list[str],
                           max_attempts: int = 2) -> Optional[dict]:
    """WebSearchで実際にリサーチしてから、情報系記事を1回のClaude呼び出しで生成する"""
    avoid = "\n".join(f"- {t}" for t in avoid_titles[:15]) or "(なし)"
    prompt = (
        f"あなたはブログ編集者です。「{genre_label}」ジャンルで、「{topic_hint}」をテーマにした"
        "ブログ記事を書いてください。\n\n"
        "まず必ずWeb検索を使って、テーマに関する具体的な事実・最新情報を調べてから執筆してください"
        "(検索せずに一般知識だけで書くことは禁止です)。\n\n"
        f"【文体・構成のルール】\n{ARTICLE_TONE_GUIDE}\n"
        "- 商品名やアフィリエイトリンクは含めない(情報系の記事のため)\n\n"
        f"【これまでに書いた記事タイトル(重複を避ける)】\n{avoid}\n\n"
        f"執筆が終わったら、次のJSON形式だけを出力してください"
        f"(前後に説明文やコードフェンスを付けず、JSONだけを出力すること):\n{ARTICLE_JSON_FORMAT}"
    )
    article = {}
    for attempt in range(max_attempts):
        feedback = "" if attempt == 0 else (
            "\n\n前回の出力はJSON形式として不正でした。前置き・コードフェンスなしで、"
            "JSONオブジェクトだけを出力し直してください。"
        )
        text = _run_claude(prompt + feedback, allowed_tools="WebSearch")
        article = _parse_json(text)
        if _is_valid(article):
            return article
    return None


def generate_product_article(genre_label: str, topic_hint: str, items: list[dict],
                              avoid_titles: list[str], max_attempts: int = 2,
                              search_keyword: str = "") -> Optional[dict]:
    """楽天APIの実データのみを根拠に商品紹介・比較記事を生成する(Web検索は使わない)"""
    keyword_rules = ""
    if search_keyword:
        keyword_rules = (
            f"- これは「{search_keyword}」を探している人に向けた、同じ種類の商品の比較記事にすること\n"
            f"- title は「{search_keyword}」をそのままの表記で先頭近くに入れ、『おすすめ』か『比較』も入れること\n"
            "- intro で、この種類を選ぶときに見るポイントを商品データから分かる範囲で2〜3個示し、"
            "各 section の body では同じポイントで違いを比べること\n"
            "- conclusion は『○○を重視するなら□□』の形で、どんな人にどれが合うかをまとめること。"
            "□□には商品の特徴が分かる短い呼び名を入れ、『商品1』のような番号は本文のどこにも書かないこと\n"
            "- 使ったような体験談は書かないこと(「使ってみた」「買ってよかった」等は禁止)\n"
        )
    facts_blocks = []
    for i, item in enumerate(items, 1):
        facts = [f"商品{i}: {item['name']}", f"価格: {item['price']:,}円(税込)"]
        if item.get("review_count"):
            facts.append(f"レビュー: 平均{item['review_average']} / {item['review_count']:,}件")
        description = (item.get("description") or "").strip()
        if description:
            if len(description) > 300:
                description = description[:300] + "…"
            facts.append(f"商品説明文: {description}")
        facts_blocks.append("\n".join(facts))
    facts_text = "\n\n".join(facts_blocks)

    avoid = "\n".join(f"- {t}" for t in avoid_titles[:15]) or "(なし)"
    names = "、".join(f"『{item['name']}』" for item in items)
    required_names = [item["name"] for item in items]

    prompt = (
        f"あなたはブログ編集者です。「{genre_label}」ジャンルで、「{topic_hint}」をテーマにした"
        f"商品紹介・比較記事を書いてください。紹介する商品は次の{len(items)}点です: {names}\n\n"
        f"【商品データ(実データ。これだけを根拠にする。Web検索はしないこと)】\n{facts_text}\n\n"
        f"【文体・構成のルール】\n{ARTICLE_TONE_GUIDE}\n"
        "- sections は商品ごとに1つずつ作ること。何番目の商品データに対応するかを"
        "product_index(1始まりの数値)に必ず入れること\n"
        "- heading は商品名をそのまま使わず、内容が伝わる自然で短い見出しにすること\n"
        "- body の中で、商品名(【商品データ】の表記のまま)に一度だけ触れること\n"
        "- 価格・購入リンクは本文に含めない(別途システム側で追加するため)\n"
        f"{keyword_rules}\n"
        f"【これまでに書いた記事タイトル(重複を避ける)】\n{avoid}\n\n"
        f"執筆が終わったら、次のJSON形式だけを出力してください"
        f"(前後に説明文やコードフェンスを付けず、JSONだけを出力すること):\n{PRODUCT_ARTICLE_JSON_FORMAT}"
    )
    article = {}
    for attempt in range(max_attempts):
        feedback = ""
        if attempt > 0:
            missing = _missing_names(article, required_names) if article else required_names
            feedback = (
                f"\n\n前回の出力は不正でした。商品名 {missing} がどこにも含まれていないか、"
                "JSON形式が不正でした。前置き・コードフェンスなしでJSONだけを出力し直してください。"
            )
        text = _run_claude(prompt + feedback, allowed_tools="")
        article = _parse_json(text)
        if _is_valid(article) and not _missing_names(article, required_names):
            return article
    return None
