#!/usr/bin/env python3
"""
サイトに掲載する記事を1本組み立てるパイプライン。

rakuten_threads_bot/main.py と同じ「ジャンルローテーション+状態ファイル」の仕組みを流用し、
1回の呼び出しで以下のどちらか1本の記事データ(dict)を返す。

  - 商品紹介・比較記事: 楽天APIの実データ(複数商品)を根拠にAIが執筆。楽天アフィリエイトリンクを本文に挿入。
  - 情報系記事: 商品を紹介しない、検索に強いお役立ち記事。広告(アドセンス)向け。

生成失敗時は None を返す(呼び出し側でログに残すだけで、テンプレートへのフォールバックは行わない
 = 実データに基づかない記事を「それっぽく」出さないための安全側の設計)。
"""

import json
import os
import random
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

import claude_writer as ai_writer  # Gemini版ai_writerから、Claude Code CLI版に切り替え(2026-09-10)
import rakuten_source

load_dotenv()

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "bot_state.json"
POSTED_FILE = BASE_DIR / "posted_articles.json"

INFO_RATIO = float(os.environ.get("SITE_ARTICLE_TYPE_RATIO", "0.5"))  # 情報系記事になる確率
ITEMS_PER_PRODUCT_ARTICLE = 3

# ── ジャンルの定義。増やす場合はここに追記するだけでローテーション対象になる ──
GENRES = [
    {
        "id": "beauty",
        "label": "メンズ美容",
        # 2026-09-29 ユーザー依頼(「美容系いらない」)で新規記事の作成を停止。
        # 公開済み記事のカテゴリページは残すため、定義自体は消さずにローテーションから外している。
        "active": False,
        "keyword": "メンズコスメ",
        "color": "#b45309",
        "photo_query": "men skincare grooming",
        "info_topics": [
            "メンズスキンケアの正しい順番",
            "清潔感を出すための髭・眉の整え方",
            "脂性肌・乾燥肌に合わせたメンズ化粧水の選び方",
            "メンズコスメの使用期限と保管方法",
            "朝だけでできる清潔感アップの習慣",
            "メンズ用日焼け止めの選び方と塗り直しのコツ",
            "加齢臭・体臭を防ぐ毎日の習慣",
            "メンズネイル・指先の清潔感を保つケア方法",
            "皮脂・テカリを抑える洗顔のポイント",
            "季節の変わり目に見直したいスキンケアの調整方法",
        ],
    },
    {
        "id": "kitchen",
        "label": "キッチン",
        "keyword": "キッチン用品",
        "color": "#0f766e",
        "photo_query": "kitchen cooking home",
        "info_topics": [
            "まな板・フライパンを長持ちさせる手入れ方法",
            "一人暮らしの自炊を時短にするキッチン収納の工夫",
            "冷蔵庫の野菜室を長持ちさせる保存のコツ",
            "キッチンのニオイ・カビ対策",
            "自炊初心者が最初に揃えるべき調理器具",
            "包丁を長く切れ味良く使うための研ぎ方・保管方法",
            "食器用スポンジ・布巾を清潔に保つ習慣",
            "作り置き・冷凍保存を上手に活用するコツ",
            "電子レンジ・オーブンの掃除とニオイ対策",
            "一人暮らしの食費を抑える買い物・保存の工夫",
        ],
    },
    {
        "id": "lifestyle",
        "label": "生活雑貨",
        "keyword": "便利グッズ",
        "color": "#6d28d9",
        "photo_query": "cozy home lifestyle organization",
        "info_topics": [
            "一人暮らしの洗濯物を生乾きにしない干し方",
            "部屋の湿気・カビ対策の基本",
            "待機電力を減らして電気代を抑える方法",
            "スマホ・ガジェットのバッテリーを長持ちさせる使い方",
            "デスク・書類が片付く仕分けルール",
            "衣替え・収納スペースを増やす工夫",
            "掃除機・フローリングワイパーの効率的な使い方",
            "来客前に短時間で片付けるコツ",
            "ゴミ出し・ゴミ袋の収納をすっきりさせる方法",
            "防災グッズの選び方と保管場所の工夫",
        ],
    },
    {
        "id": "gadget",
        "label": "ガジェット",
        "keyword": "スマホアクセサリー",
        "color": "#dc2626",
        "photo_query": "tech gadgets desk setup",
        "info_topics": [
            "モバイルバッテリーの選び方と正しい使い方",
            "スマホの充電を長持ちさせるバッテリー節約術",
            "ワイヤレスイヤホンを長く使うためのお手入れ方法",
            "在宅ワークが捗るデスク周りのガジェット活用術",
            "スマホの画面・カメラレンズを傷つけない扱い方",
            "外出先で役立つ充電・通信トラブルの備え方",
            "PC周辺機器のケーブル・配線をすっきりまとめるコツ",
            "スマホストレージ不足を解消する整理方法",
        ],
    },
    {
        "id": "fashion",
        "label": "メンズファッション",
        "keyword": "メンズファッション",
        "color": "#1d4ed8",
        "photo_query": "men fashion casual style",
        "info_topics": [
            "清潔感のあるメンズコーデの基本ルール",
            "シワになりにくい服の選び方と収納方法",
            "革靴・スニーカーを長持ちさせるお手入れ方法",
            "体型カバーに役立つメンズ服の選び方",
            "季節の変わり目に使える羽織り・重ね着のコツ",
            "オフィスカジュアルで失敗しない服選び",
            "靴下・インナーなど見えない部分の清潔感の保ち方",
            "自宅でできる衣類のシミ・ニオイ対策",
        ],
    },
    {
        "id": "appliance",
        "label": "便利家電・最新家電",
        "keyword": "時短家電",
        "color": "#ca8a04",
        "photo_query": "modern home appliances living room",
        "info_topics": [
            "最新の時短家電で家事の時間は実際にどれだけ減るのか",
            "一人暮らしに本当に必要な家電と、後回しでいい家電",
            "省エネ性能の見方と、家電ごとの電気代の比べ方",
            "ロボット掃除機が向いている部屋・向かない部屋",
            "工事不要タイプの食洗機を導入する前に確認すること",
            "衣類乾燥除湿機とドラム式洗濯乾燥機の使い分け",
            "電気圧力鍋・自動調理鍋でできることとできないこと",
            "家電の買い替えどきの判断基準と、正しい処分方法",
            "スマートプラグ・スマートリモコンから始めるスマート家電",
            "空気清浄機・加湿器を選ぶときに見るべき数値",
        ],
    },
    {
        "id": "apple",
        "label": "Apple最新情報",
        "keyword": "iPhoneアクセサリー",
        "color": "#52525b",
        "photo_query": "apple devices iphone macbook desk",
        "info_topics": [
            "最新iPhoneの新機能と、前モデルからの変更点",
            "iOSの最新アップデートで追加された便利機能の使い方",
            "iPhoneのバッテリー劣化を確認して寿命を延ばす方法",
            "最新Apple Watchでできることと、健康機能の使い方",
            "MacとiPhoneの連携機能で作業を速くする方法",
            "AirPodsの最新機能とノイズキャンセリングの設定",
            "iCloudの無料枠内でiPhoneの写真・データを管理する方法",
            "iPadを仕事・勉強で使いこなす設定とアクセサリー選び",
            "古いiPhone・iPadを下取りや売却に出す前にやること",
            "Appleの最新発表のうち、既存ユーザーに関係がある変更点",
        ],
    },
    {
        "id": "china_gadget",
        "label": "Huawei・中華ガジェット",
        "keyword": "スマートウォッチ",
        "color": "#be185d",
        "photo_query": "smartwatch wearable technology gadgets",
        "info_topics": [
            "Huaweiの最新スマートウォッチでできることと注意点",
            "中華スマホ・ガジェットを買う前に確認したい技適マークの話",
            "Xiaomi・Ankerなどコスパ重視ブランドの選び方",
            "格安ワイヤレスイヤホンの品質を見分けるポイント",
            "中華ガジェットの保証・サポートとトラブル時の対処法",
            "スマートリング・活動量計の測定精度と使いどころ",
            "海外通販と国内正規品、どちらで買うべきかの判断基準",
            "最新の格安タブレットで実際にできること・できないこと",
        ],
    },
]


# 商品紹介記事は「1記事=1種類」にする(2026-11-07)。ジャンル全体の広い語で検索すると
# 「福袋・トング・ボトルスタンド」のように無関係な3点が並び、読者にも検索にも合わないため。
# 実際に検索されやすい物の名前を並べる。商品名に含まれる形で書く(_pick_same_type_items が名前一致を見る)。
PRODUCT_KEYWORDS = {
    "kitchen": [
        "水切りラック", "調味料ボトル", "キッチンバサミ", "電気ケトル", "シリコンスチーマー", "サラダスピナー",
        "縦型ピーラー", "キッチンスケール", "ハンドミキサー", "コーヒーミル", "真空断熱タンブラー", "低温調理器",
        "エアフライヤー", "電気圧力鍋", "オイルスプレー", "排気口カバー", "スポンジラック", "真空パック器",
        "シリコン菜箸", "回転トレー", "ハンディチョッパー", "クリップシーラー", "フライパンカバー", "水切りボウル",
        "キッチンワゴン", "解凍プレート", "キッチンマット", "壁掛けゴミ箱",
    ],
    "lifestyle": [
        "珪藻土バスマット", "突っ張り棒", "圧縮袋", "ネックピロー", "折りたたみハンガー", "有孔ボード",
        "隙間ブラシ", "ケーブルクリップ", "テレビスタンド", "ブックスタンド", "ゴミ袋ホルダー", "ヨガマット",
        "温湿度計", "袋止めクリップ", "滑らないハンガー", "ヘアドライタオル", "人感センサーライト", "耳栓",
        "メガネケース", "折りたたみバケツ", "ランドリーバスケット", "フォームローラー",
    ],
    "gadget": [
        "モバイルバッテリー", "車載スマホホルダー", "スマホスタンド", "巻き取りケーブル", "ワイヤレス充電器",
        "紛失防止タグ", "スマホリング", "自撮り棒", "モニタースタンド", "トラックボール", "カードリーダー",
        "Bluetoothスピーカー", "USBハブ", "デスクライト", "モニターライト",
    ],
    "fashion": [
        "裏起毛パンツ", "ダウンジャケット", "ダウンベスト", "ニットカーディガン", "チノパン", "ボアジャケット",
        "ワイドパンツ", "リュック", "ショルダーバッグ", "スニーカー", "マフラー", "ニット帽", "レザーベルト", "長財布",
    ],
    "appliance": [
        "衣類スチーマー", "布団乾燥機", "ふとんクリーナー", "ハンディクリーナー", "衣類乾燥除湿機", "サーキュレーター",
        "パネルヒーター", "加湿空気清浄機", "スチーム式加湿器", "電気湯たんぽ", "オイルヒーター", "卓上IH",
        "毛玉クリーナー", "ロボット掃除機", "電動歯ブラシ", "スマートプラグ", "スマートリモコン", "ホットプレート",
        "オーブントースター",
    ],
    "apple": [
        "iPhoneケース", "ガラスフィルム", "MagSafe充電器", "Apple Watchバンド", "AirPodsケース", "iPadケース",
        "Lightningケーブル", "USB-Cケーブル", "iPhoneスタンド", "カメラレンズカバー",
    ],
    "china_gadget": [
        "スマートウォッチ", "スマートバンド", "ワイヤレスイヤホン", "骨伝導イヤホン", "プロジェクター", "スマートリング",
        "ポータブル電源", "ドライブレコーダー", "アクションカメラ",
    ],
}
# ジャンルの対象を絞る語。検索に足し、商品名にも含むものだけを選ぶ(メンズの記事にレディース商品を混ぜない)
PRODUCT_REQUIRED_WORD = {"fashion": "メンズ"}
PRODUCT_EXCLUDE_WORDS = ("福袋", "訳あり", "アウトレット", "ガチャ", "中古", "キッズ")
MIN_REVIEW_COUNT = 10
MIN_REVIEW_AVERAGE = 4.0
MAX_ITEM_PRICE = 50000
KEYWORD_TRIES = 4  # 1回の記事作成で調べる種類の数(楽天APIの呼びすぎを防ぐ)


def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_state() -> dict:
    return load_json(STATE_FILE, {})


def save_state(state: dict):
    save_json(STATE_FILE, state)


def load_posted() -> list[dict]:
    return load_json(POSTED_FILE, [])


def save_posted(posted: list[dict]):
    save_json(POSTED_FILE, posted)


def pick_genre(state: dict) -> dict:
    # "active": False のジャンルは飛ばす(カテゴリページ用に定義だけ残しているもの)
    idx = state.get("last_genre_index", -1)
    for _ in range(len(GENRES)):
        idx = (idx + 1) % len(GENRES)
        if GENRES[idx].get("active", True):
            break
    state["last_genre_index"] = idx
    return GENRES[idx]


def pick_info_topic(genre: dict, state: dict) -> str:
    """まだ使っていないテーマを順番に選ぶ。全テーマを使い切ったら最初から回す。
    以前はインデックスを単純にインクリメントするだけだったため、状態の保存漏れ(手動で
    作ったデモ記事など)があると同じインデックスに戻って同じテーマを再生成し、
    ほぼ同じ内容の記事が重複してしまう問題があった。使用済みテーマそのものを記録する
    方式にして、順序がずれても同じテーマを選び直さないようにしている。"""
    topics = genre["info_topics"]
    key = f"used_info_topics_{genre['id']}"
    used = state.get(key, [])
    remaining = [t for t in topics if t not in used]
    if not remaining:
        used = []
        remaining = topics
    topic = remaining[0]
    used = used + [topic]
    state[key] = used
    return topic


def slugify(genre_id: str, article_type: str) -> str:
    today = date.today().strftime("%Y%m%d")
    existing = load_posted()
    seq = sum(1 for a in existing if a["slug"].startswith(f"{today}-")) + 1
    return f"{today}-{genre_id}-{article_type}-{seq}"


def _titles_for_genre(posted: list[dict], genre_id: str) -> list[str]:
    return [a["title"] for a in posted if a.get("genre_id") == genre_id]


def _used_item_ids(posted: list[dict]) -> set:
    used = set()
    for a in posted:
        used.update(a.get("item_ids", []))
    return used


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _attach_items_to_sections(sections: list[dict], items: list[dict]):
    """各セクションに対応する商品をproduct_index(1始まり、AIが付与)から特定し、
    section["item"] に紐付ける。見出しは商品名そのままではなく自然な文章にできるようにするため、
    見出しの文字列一致ではなくインデックスで対応付ける設計にしている。"""
    for section in sections:
        idx = section.get("product_index")
        item = None
        if isinstance(idx, int) and 1 <= idx <= len(items):
            item = items[idx - 1]
        elif isinstance(idx, str) and idx.isdigit() and 1 <= int(idx) <= len(items):
            item = items[int(idx) - 1]
        else:
            # AIがproduct_indexを付け忘れた場合のフォールバック(空白差異を無視した名前一致)
            heading_norm = _normalize_ws(section.get("heading", ""))
            body_norm = _normalize_ws(section.get("body", ""))
            item = next(
                (i for i in items if _normalize_ws(i["name"]) in heading_norm + body_norm),
                None,
            )
        section["item"] = item


def _add_section_ids(sections: list[dict]):
    """目次(TOC)用に各セクションへ一意なアンカーID(section-1, section-2, ...)を付与する"""
    for i, section in enumerate(sections, 1):
        section["id"] = f"section-{i}"


def build_info_article(genre: dict, posted: list[dict], state: dict) -> dict | None:
    topic = pick_info_topic(genre, state)
    print(f"  情報系記事を作成します(ジャンル: {genre['label']} / テーマ: {topic})")
    avoid = _titles_for_genre(posted, genre["id"])
    raw = ai_writer.generate_info_article(genre["label"], topic, avoid)
    if raw is None:
        print("  [エラー] 記事生成に失敗しました")
        return None

    _add_section_ids(raw["sections"])

    slug = slugify(genre["id"], "info")
    return {
        "slug": slug,
        "title": raw["title"],
        "meta_description": raw["meta_description"],
        "genre_id": genre["id"],
        "genre_label": genre["label"],
        "genre_color": genre.get("color", "#374151"),
        "photo_query": genre.get("photo_query", ""),
        "type": "info",
        "topic": topic,
        "intro": raw["intro"],
        "sections": raw["sections"],
        "conclusion": raw["conclusion"],
        "affiliate_items": [],
        "published_at": datetime.now().isoformat(timespec="seconds"),
        "item_ids": [],
    }


PROMO_NAME_WORD = re.compile(r"送料無料|ポイント|クーポン|\d+倍|\d+%OFF|セール|限定|あす楽|即納|ランキング|楽天|プレゼント|ギフト|父の日|母の日|クリスマス")


def _clean_item_name(name: str) -> str:
    """楽天の商品名の先頭や途中にある販促の飾り(【楽天1位】＼クーポン／など)を除く"""
    raw = name
    name = re.sub(r"【[^】]*】|＼[^／]*／|\[[^\]]*\]|★[^★]*★|◆[^◆]*◆|楽天\d+位", " ", name)
    # 2026-11-07 品質: 楽天の商品名は検索用の単語の羅列なので、そのままだと読めない。語を残したまま短くする
    words = [w for w in re.split(r"[\s//|｜]+", name) if w and not PROMO_NAME_WORD.search(w)]
    out, seen = [], set()
    for w in words:
        if w.lower() in seen:
            continue
        if len("".join(out)) + len(w) > 22 and out:
            break
        seen.add(w.lower())
        out.append(w)
    return " ".join(out).strip() or re.sub(r"\s+", " ", name).strip() or raw


def _pick_same_type_items(keyword: str, items: list[dict], used: set, required_word: str = "") -> list[dict]:
    """同じ種類の商品だけを比較できるよう、商品名にキーワードを含む高評価の商品を選ぶ。
    同じ店の商品は1件まで(実質同じ物が3つ並ぶのを防ぐ)。"""
    key = _normalize_ws(keyword).lower()
    picked, shops = [], set()
    for item in items:
        name = item["name"]
        if (item["id"] in used
                or key not in _normalize_ws(name).lower()
                or required_word not in name
                or any(w in name for w in PRODUCT_EXCLUDE_WORDS)
                or (item.get("review_count") or 0) < MIN_REVIEW_COUNT
                or float(item.get("review_average") or 0) < MIN_REVIEW_AVERAGE
                or (item.get("price") or 0) > MAX_ITEM_PRICE
                or item.get("shop") in shops):
            continue
        shops.add(item.get("shop"))
        picked.append(item)
        if len(picked) == ITEMS_PER_PRODUCT_ARTICLE:
            break
    return picked


def _find_product_keyword(genre: dict, posted: list[dict], state: dict) -> tuple[str, list[dict]] | None:
    """まだ使っていない種類を順に調べ、3商品そろう最初の種類を返す。
    そろわなかった種類も使用済みにして、次回また同じ検索をしないようにする。"""
    keywords = PRODUCT_KEYWORDS.get(genre["id"], [])
    state_key = f"used_product_keywords_{genre['id']}"
    tried = state.get(state_key, [])
    remaining = [k for k in keywords if k not in tried]
    if not remaining:
        tried, remaining = [], list(keywords)
    used = _used_item_ids(posted)
    required_word = PRODUCT_REQUIRED_WORD.get(genre["id"], "")
    found = None
    for keyword in remaining[:KEYWORD_TRIES]:
        try:
            items = rakuten_source.fetch_items(keyword=f"{required_word} {keyword}".strip())
        except Exception as e:
            print(f"  [エラー] 楽天APIの商品取得に失敗しました: {e}")
            break
        tried = tried + [keyword]
        picked = _pick_same_type_items(keyword, items, used, required_word)
        if len(picked) == ITEMS_PER_PRODUCT_ARTICLE:
            found = (keyword, picked)
            break
        print(f"  「{keyword}」は条件に合う商品が{len(picked)}件だけのため見送ります")
    state[state_key] = tried
    return found


def build_product_article(genre: dict, posted: list[dict], state: dict) -> dict | None:
    print(f"  商品紹介記事を作成します(ジャンル: {genre['label']})")
    found = _find_product_keyword(genre, posted, state)
    if found is None:
        print(f"  {genre['label']}に同じ種類で比較できる新規商品がありませんでした")
        return None
    keyword, new_items = found
    print(f"  比較する種類: {keyword}")

    # 楽天の商品名は80〜150字の長い販促文になっていることが多く、AIに一字一句そのまま
    # 再現させるのは非現実的(全角スペースの微妙な差異などで容易に不一致になる)。
    # rakuten_threads_bot/main.py と同じく40字に短縮した表示名を「正式名称」として扱う。
    for item in new_items:
        item["name"] = _clean_item_name(item["name"])
        if len(item["name"]) > 40:
            item["name"] = item["name"][:40] + "…"

    topic = f"{keyword}のおすすめ{len(new_items)}選と選び方"
    avoid = _titles_for_genre(posted, genre["id"])
    raw = ai_writer.generate_product_article(genre["label"], topic, new_items, avoid, search_keyword=keyword)
    if raw is None:
        print("  [エラー] 記事生成に失敗しました(商品名が正しく含まれない等)")
        return None
    if keyword not in raw["title"]:
        raw["title"] = f"{keyword}おすすめ{len(new_items)}選|{raw['title']}"

    _attach_items_to_sections(raw["sections"], new_items)
    _add_section_ids(raw["sections"])

    slug = slugify(genre["id"], "product")
    return {
        "slug": slug,
        "title": raw["title"],
        "meta_description": raw["meta_description"],
        "genre_id": genre["id"],
        "genre_label": genre["label"],
        "genre_color": genre.get("color", "#374151"),
        "photo_query": genre.get("photo_query", ""),
        "type": "product",
        "intro": raw["intro"],
        "sections": raw["sections"],
        "conclusion": raw["conclusion"],
        "affiliate_items": new_items,
        "published_at": datetime.now().isoformat(timespec="seconds"),
        "item_ids": [i["id"] for i in new_items],
    }


def generate_article() -> dict | None:
    """記事1本を生成する。失敗時はNoneを返す(呼び出し側でログ・リトライを判断)。"""
    state = load_state()
    posted = load_posted()
    genre = pick_genre(state)

    is_info = random.random() < INFO_RATIO
    article = None
    if is_info:
        article = build_info_article(genre, posted, state)
    else:
        article = build_product_article(genre, posted, state)
        if article is None:
            # その場でジャンルを変えて情報系記事にフォールバック(商品が尽きていても記事は出す)
            print("  商品紹介記事が作れなかったため、情報系記事にフォールバックします")
            article = build_info_article(genre, posted, state)

    save_state(state)
    return article
