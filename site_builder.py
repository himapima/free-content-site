#!/usr/bin/env python3
"""
記事データ(dict)からJinja2テンプレートを使って静的HTMLを生成する。
GitHub Pagesなど静的ホスティングにそのまま置ける docs/ フォルダを作る(GitHub Pagesの「mainブランチ/docsフォルダ」設定にそのまま対応)。
"""

import json
import os
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

import content_pipeline

load_dotenv()

BASE_DIR = Path(__file__).parent
SITE_DIR = BASE_DIR / "docs"
ARTICLES_DIR = SITE_DIR / "articles"
CATEGORIES_DIR = SITE_DIR / "categories"
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "").rstrip("/")

SITE_NAME = "暮らしと、ちょっといいもの。"
SITE_TAGLINE = "実際のレビューをもとに、暮らしを少し良くするアイテムと知恵をお届けします。"

_env = Environment(loader=FileSystemLoader(str(BASE_DIR / "templates")), autoescape=True)

ALL_CATEGORIES = [{"id": g["id"], "label": g["label"], "color": g["color"]} for g in content_pipeline.GENRES]
# ナビに出すカテゴリー。ジャンルを新しく増やした直後はまだ記事が0本で、そのまま出すと
# 「開いても何も無いページ」がメニューに並んでしまう。記事が1本でも入った時点で自動的に
# メニュー・サイトマップへ現れるよう、build_site() の時点で絞り込む。
NAV_CATEGORIES = list(ALL_CATEGORIES)


def _refresh_nav(posted: list[dict]):
    global NAV_CATEGORIES
    have = {a.get("genre_id") for a in posted}
    NAV_CATEGORIES = [c for c in ALL_CATEGORIES if c["id"] in have] or list(ALL_CATEGORIES)


def _canonical(path: str) -> str:
    return f"{SITE_BASE_URL}/{path}" if SITE_BASE_URL else ""


def _related_articles(article: dict, all_articles: list[dict], max_items: int = 3) -> list[dict]:
    """同じジャンルの他の記事を新しい順に返す(なければ他ジャンルの新着で埋める)"""
    others = [a for a in all_articles if a["slug"] != article["slug"]]
    same_genre = [a for a in others if a.get("genre_id") == article.get("genre_id")]
    same_genre.sort(key=lambda a: a["published_at"], reverse=True)
    result = same_genre[:max_items]
    if len(result) < max_items:
        rest = [a for a in others if a not in result]
        rest.sort(key=lambda a: a["published_at"], reverse=True)
        result += rest[: max_items - len(result)]
    return result


def _article_json_ld(article: dict) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article["title"],
        "description": article["meta_description"],
        "datePublished": article["published_at"],
        "image": _canonical(f"images/{article['slug']}.png") or f"../images/{article['slug']}.png",
        "author": {"@type": "Organization", "name": SITE_NAME},
        "publisher": {"@type": "Organization", "name": SITE_NAME},
    }
    return json.dumps(data, ensure_ascii=False)


def render_article(article: dict, all_articles: list[dict]):
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    _refresh_nav(all_articles)
    html = _env.get_template("article.html").render(
        article=article,
        related=_related_articles(article, all_articles),
        site_name=SITE_NAME,
        nav_categories=NAV_CATEGORIES,
        json_ld=_article_json_ld(article),
        title=f"{article['title']} | {SITE_NAME}",
        description=article["meta_description"],
        canonical_url=_canonical(f"articles/{article['slug']}.html"),
        og_image=_canonical(f"images/{article['slug']}.png"),
        root="../",
        year=date.today().year,
    )
    (ARTICLES_DIR / f"{article['slug']}.html").write_text(html, encoding="utf-8")


def render_index(posted: list[dict], max_items: int = 30):
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    recent = sorted(posted, key=lambda a: a["published_at"], reverse=True)[:max_items]
    featured, rest = (recent[0], recent[1:]) if recent else (None, [])
    html = _env.get_template("index.html").render(
        featured=featured,
        articles=rest,
        site_name=SITE_NAME,
        tagline=SITE_TAGLINE,
        nav_categories=NAV_CATEGORIES,
        title=f"{SITE_NAME} | {SITE_TAGLINE}",
        description=SITE_TAGLINE,
        canonical_url=_canonical("index.html"),
        og_image=_canonical(f"images/{featured['slug']}.png") if featured else "",
        root="",
        year=date.today().year,
    )
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")


def render_category_pages(posted: list[dict]):
    CATEGORIES_DIR.mkdir(parents=True, exist_ok=True)
    for genre in content_pipeline.GENRES:
        articles = sorted(
            (a for a in posted if a.get("genre_id") == genre["id"]),
            key=lambda a: a["published_at"],
            reverse=True,
        )
        if not articles:
            continue  # まだ記事が無いジャンルは、空のページを作らない
        html = _env.get_template("category.html").render(
            articles=articles,
            genre=genre,
            site_name=SITE_NAME,
            nav_categories=NAV_CATEGORIES,
            title=f"{genre['label']}の記事一覧 | {SITE_NAME}",
            description=f"{SITE_NAME}の{genre['label']}カテゴリーの記事一覧です。",
            canonical_url=_canonical(f"categories/{genre['id']}.html"),
            og_image="",
            root="../",
            year=date.today().year,
        )
        (CATEGORIES_DIR / f"{genre['id']}.html").write_text(html, encoding="utf-8")


def write_sitemap(posted: list[dict]):
    if not SITE_BASE_URL:
        return  # 公開URLが未設定の間はサイトマップを作らない(間違った絶対URLを埋め込まないため)
    urls = [f"{SITE_BASE_URL}/index.html"]
    urls += [f"{SITE_BASE_URL}/articles/{a['slug']}.html" for a in posted]
    urls += [f"{SITE_BASE_URL}/categories/{c['id']}.html" for c in NAV_CATEGORIES]
    urls += [f"{SITE_BASE_URL}/{p['slug']}.html" for p in STATIC_PAGES]
    body = "\n".join(f"  <url><loc>{escape(u)}</loc></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'
    (SITE_DIR / "sitemap.xml").write_text(xml, encoding="utf-8")


def write_robots():
    lines = ["User-agent: *", "Allow: /"]
    if SITE_BASE_URL:
        lines.append(f"Sitemap: {SITE_BASE_URL}/sitemap.xml")
    (SITE_DIR / "robots.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


STATIC_PAGES = [
    {
        "slug": "about",
        "heading": "このサイトについて",
        "body": """
<p>「{site_name}」は、暮らしを少し良くするアイテムや知恵を紹介するメディアです。</p>
<h2>運営方針</h2>
<p>商品紹介記事は、楽天市場に掲載されている実際の価格・レビュー件数・商品説明のみを根拠に作成しています。実際に使用していない効果や、商品ページに記載のないスペックを書くことはありません。</p>
<p>お役立ち情報の記事は、インターネット上の情報を調査した上で、暮らしに役立つ知識をまとめています。</p>
<h2>収益について</h2>
<p>当サイトは楽天アフィリエイトプログラムに参加しており、商品紹介記事のリンクから購入いただくと、サイト運営者に紹介料が入る場合があります。商品紹介記事にはその旨(PR表記)を明記しています。</p>
<h2>運営者</h2>
<p>当サイトは個人が運営しています。お問い合わせは各記事末尾のコメント欄よりお願いいたします。</p>
""",
    },
    {
        "slug": "privacy",
        "heading": "プライバシーポリシー",
        "body": """
<p>「{site_name}」(以下「当サイト」)における、個人情報の取り扱いについて説明します。</p>
<h2>アクセス解析・広告について</h2>
<p>当サイトは、サービス向上のためアクセス解析ツールや広告配信サービスを利用する場合があります。これらのサービスは、Cookie等を利用して個人を特定する情報を含まずにアクセス情報を収集することがあります。この情報は各サービス提供者のプライバシーポリシーに基づいて管理されます。</p>
<h2>アフィリエイトプログラムについて</h2>
<p>当サイトは楽天アフィリエイトプログラム等、各種アフィリエイトプログラムを利用しています。これらのプログラムを通じて商品・サービスを紹介し、成果に応じた収益を得る場合があります。</p>
<h2>コメント機能について</h2>
<p>記事へのコメントは匿名で投稿でき、アカウント登録は不要です。投稿内容には、法令に違反するもの・第三者の権利を侵害するもの・公序良俗に反するものを含めないでください。当サイト運営者が不適切と判断したコメントは、事前の通知なく削除する場合があります。</p>
<h2>免責事項</h2>
<p>当サイトのコンテンツ・情報について、できる限り正確な情報を提供するよう努めておりますが、正確性や安全性を保証するものではありません。当サイトの情報を用いて行う行動につきましては、ご自身の責任・判断で行っていただきますようお願いいたします。</p>
<h2>プライバシーポリシーの変更</h2>
<p>当サイトは、本ポリシーの内容を予告なく変更する場合があります。変更後のプライバシーポリシーは、本ページに掲載した時点から効力を生じるものとします。</p>
""",
    },
]


def render_static_pages():
    for page in STATIC_PAGES:
        html = _env.get_template("page.html").render(
            page_heading=page["heading"],
            page_body=page["body"].format(site_name=SITE_NAME),
            site_name=SITE_NAME,
            nav_categories=NAV_CATEGORIES,
            title=f"{page['heading']} | {SITE_NAME}",
            description=page["heading"],
            canonical_url=_canonical(f"{page['slug']}.html"),
            og_image="",
            root="",
            year=date.today().year,
        )
        (SITE_DIR / f"{page['slug']}.html").write_text(html, encoding="utf-8")


def build_site(posted: list[dict]):
    """全記事分のindex/カテゴリページ/sitemap/robotsを再生成する(新しい記事を1本作った後などに呼ぶ)"""
    _refresh_nav(posted)
    render_index(posted)
    render_category_pages(posted)
    render_static_pages()
    write_sitemap(posted)
    write_robots()


def rebuild_all_pages():
    """posted_articles.jsonに保存済みの全記事データから、docs/以下を丸ごと再生成する。
    デザイン(テンプレート/CSS)だけを変更したときに、AIを呼び直さず全ページへ反映するために使う。
    """
    posted = content_pipeline.load_posted()
    for article in posted:
        render_article(article, posted)
    build_site(posted)
    return len(posted)


if __name__ == "__main__":
    count = rebuild_all_pages()
    print(f"{count}件の記事ページを再生成しました")
