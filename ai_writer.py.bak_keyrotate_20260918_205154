#!/usr/bin/env python3
"""
記事生成用のGemini API呼び出しユーティリティ。

Google Gemini API(無料枠)を使用する。有料のAnthropic APIは使わない。
GEMINI_API_KEY は https://aistudio.google.com/apikey で無料発行できる
(rakuten_threads_bot・youtube_jido・note_auto_bot と同じキーを共有してもよい)。

rakuten_threads_bot の ai_pipeline.py と同じ「リサーチ→執筆→品質チェック」の
パイプラインを、Threads投稿用の短文ではなく、SEO向けの長文記事用に書き直したもの。
"""

import json
import re
import time
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

RESEARCH_MODEL = "gemini-3.6-flash"
WRITER_MODEL = "gemini-3.6-flash"
QUALITY_MODEL = "gemini-3.6-flash"

MAX_RETRIES = 3

ARTICLE_TONE_GUIDE = """\
文体・構成のルール:
- 丁寧で読みやすい「です・ます」調。断定しすぎず、根拠を示しながら説明する。
- 命令形(〜しろ、〜せよ)や乱暴なスラングは使わない。
- タイトルは検索されそうな具体的なキーワードを含み、30字程度にする。
- 見出し(H2)を3〜5個に分け、それぞれ200〜400字程度で説明する。
- 誇張・断定的な効能表現(「必ず」「絶対」など)は避ける。
- 【参考情報】に書かれている事実だけを根拠にし、書かれていない効果・スペック・
  数値は絶対に作り出さない。
"""


def _client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY が設定されていません")
    return genai.Client(api_key=GEMINI_API_KEY)


def _generate(prompt: str, model: str, json_mode: bool = False, use_search: bool = False) -> str:
    """Gemini APIを呼び出し、無料枠のレート制限(429)には自動リトライする"""
    client = _client()
    config_kwargs = {}
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    if use_search:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            return (response.text or "").strip()
        except Exception as e:
            last_error = e
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                time.sleep(5)
            elif attempt < MAX_RETRIES - 1:
                time.sleep(2)
    raise RuntimeError(f"Gemini APIの呼び出しに失敗しました: {last_error}")


def _parse_json(text: str) -> dict:
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}


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


def research_agent(topic_hint: str) -> str:
    """記事のテーマについて、執筆前の下調べ(構成案・切り口の整理)を行う。

    無料枠の新規APIキーではGoogle検索連携(グラウンディング)が429エラーになり使えないため、
    Web検索は行わず、モデル自身の一般知識のみで構成案を作る。事実の捏造を避けるため、
    具体的な統計値や「最新の調査によると」等の出典を装った記述はしないよう明示的に指示する。
    """
    prompt = (
        f"「{topic_hint}」について、記事を書く前の構成案を作ってください。\n"
        "- 一般に広く知られている内容・常識的な範囲の情報だけを使うこと\n"
        "- 具体的な統計値・調査結果・「〜という調査があります」のような出典を伴う言い回しは"
        "でっち上げないこと(事実確認できないため)\n"
        "- 記事で扱うと良さそうな切り口を2〜3個、箇条書きで400字以内にまとめてください"
    )
    return _generate(prompt, RESEARCH_MODEL, use_search=False)


def write_info_article(genre_label: str, topic_hint: str, research_notes: str,
                        avoid_titles: list[str], feedback: Optional[str] = None) -> dict:
    """リサーチ内容を踏まえて、商品を紹介しない情報系の記事を書く"""
    avoid = "\n".join(f"- {t}" for t in avoid_titles[:15]) or "(なし)"
    prompt = (
        f"「{genre_label}」ジャンルで、「{topic_hint}」をテーマにしたブログ記事を書いてください。\n\n"
        f"【リサーチ内容】\n{research_notes}\n\n"
        f"【文体・構成のルール】\n{ARTICLE_TONE_GUIDE}\n"
        "- 商品名やアフィリエイトリンクは含めない(情報系の記事のため)\n\n"
        f"【これまでに書いた記事タイトル(重複を避ける)】\n{avoid}\n\n"
        f"次のJSON形式だけで出力してください(他の文章は一切出力しないでください):\n{ARTICLE_JSON_FORMAT}"
    )
    if feedback:
        prompt += f"\n\n【前回案への品質チェックのフィードバック。これを踏まえて書き直してください】\n{feedback}"
    text = _generate(prompt, WRITER_MODEL, json_mode=True)
    return _parse_json(text)


def write_product_article(genre_label: str, topic_hint: str, items: list[dict],
                           avoid_titles: list[str], feedback: Optional[str] = None) -> dict:
    """楽天APIの実データ(複数商品)だけを根拠に、比較・紹介系の記事を書く"""
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
    prompt = (
        f"「{genre_label}」ジャンルで、「{topic_hint}」をテーマにした商品紹介・比較記事を書いてください。\n"
        f"紹介する商品は次の{len(items)}点です: {names}\n\n"
        f"【商品データ(実データ。これだけを根拠にする)】\n{facts_text}\n\n"
        f"【文体・構成のルール】\n{ARTICLE_TONE_GUIDE}\n"
        "- sections は商品ごとに1つずつ作ること。何番目の商品データに対応するかを"
        "product_index(1始まりの数値)に必ず入れること\n"
        "- heading は商品名をそのまま使わず、内容が伝わる自然で短い見出しにすること"
        "(例:「保湿ケアを1本で済ませたい人に」など)\n"
        "- body の中で、商品名(【商品データ】の表記のまま)に一度だけ触れること\n"
        "- 価格・購入リンクは本文に含めない(別途システム側で追加するため)\n\n"
        f"【これまでに書いた記事タイトル(重複を避ける)】\n{avoid}\n\n"
        f"次のJSON形式だけで出力してください(他の文章は一切出力しないでください):\n{PRODUCT_ARTICLE_JSON_FORMAT}"
    )
    if feedback:
        prompt += f"\n\n【前回案への品質チェックのフィードバック。これを踏まえて書き直してください】\n{feedback}"
    text = _generate(prompt, WRITER_MODEL, json_mode=True)
    return _parse_json(text)


def quality_agent(article: dict, required_names: Optional[list[str]] = None) -> dict:
    """記事の文体・事実逸脱・必須キーワードをチェックし、合否とフィードバックを返す"""
    required_names = required_names or []
    name_checks = "\n".join(f"- 「{n}」が表記を変えずにどこかに含まれていること" for n in required_names)
    prompt = (
        "以下はブログ記事の下書き(JSON)です。次の基準でチェックし、JSON形式だけで回答してください"
        "(他の文章は一切出力しないでください)。\n\n"
        f"基準:\n{ARTICLE_TONE_GUIDE}\n"
        "- title/meta_description/intro/sections/conclusion が全て空でないこと\n"
        f"{name_checks}\n\n"
        f"【下書き】\n{json.dumps(article, ensure_ascii=False)}\n\n"
        '出力するJSON形式: {"pass": true または false, "feedback": "NGな場合の具体的な理由と直し方。OKなら空文字"}'
    )
    text = _generate(prompt, QUALITY_MODEL, json_mode=True)
    result = _parse_json(text)
    return result if "pass" in result else {"pass": True, "feedback": ""}


REQUIRED_KEYS = {"title", "meta_description", "intro", "sections", "conclusion"}


def _is_valid(article: dict) -> bool:
    if not REQUIRED_KEYS.issubset(article.keys()):
        return False
    if not article["title"] or not article["sections"]:
        return False
    return True


def generate_info_article(genre_label: str, topic_hint: str, avoid_titles: list[str],
                           max_attempts: int = 2) -> Optional[dict]:
    """リサーチ→執筆→品質チェックのパイプラインで情報系記事を生成する"""
    notes = research_agent(f"{genre_label} {topic_hint}")
    feedback = None
    article = {}
    for _ in range(max_attempts):
        article = write_info_article(genre_label, topic_hint, notes, avoid_titles, feedback=feedback)
        if not _is_valid(article):
            feedback = "JSON形式が不正、または必須項目が空でした。指定のJSON形式を厳密に守ってください。"
            continue
        result = quality_agent(article)
        if result.get("pass"):
            return article
        feedback = result.get("feedback") or "基準を満たしていません。"
    return article if _is_valid(article) else None


def _normalize_ws(text: str) -> str:
    """空白(半角/全角)の差異を無視して比較するための正規化。改行・スペースを全て除去する。"""
    return re.sub(r"\s+", "", text)


def _missing_names(article: dict, required_names: list[str]) -> list[str]:
    dumped = _normalize_ws(json.dumps(article, ensure_ascii=False))
    return [n for n in required_names if _normalize_ws(n) not in dumped]


def generate_product_article(genre_label: str, topic_hint: str, items: list[dict],
                              avoid_titles: list[str], max_attempts: int = 2) -> Optional[dict]:
    """楽天APIの実データのみを根拠に商品紹介・比較記事を生成する"""
    required_names = [item["name"] for item in items]
    feedback = None
    article = {}
    for _ in range(max_attempts):
        article = write_product_article(genre_label, topic_hint, items, avoid_titles, feedback=feedback)
        if not _is_valid(article):
            feedback = "JSON形式が不正、または必須項目が空でした。指定のJSON形式を厳密に守ってください。"
            continue
        missing = _missing_names(article, required_names)
        if missing:
            feedback = f"商品名 {missing} がどこにも含まれていません。省略・改変せずに使ってください。"
            continue
        # 商品名の一致は上のプログラム側チェック(空白の差異は許容)で確認済みのため、
        # ここでのAI品質チェックはトーン・構成のみを対象にする(名前の再チェックはしない)
        result = quality_agent(article)
        if result.get("pass"):
            return article
        feedback = result.get("feedback") or "基準を満たしていません。"
    if article and not _missing_names(article, required_names):
        return article
    return None
