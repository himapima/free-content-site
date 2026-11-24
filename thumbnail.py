#!/usr/bin/env python3
"""
記事タイトルからOG画像(1280x670)をPillowで自動生成する。
note_auto_bot/thumbnail_generator.py を移植したもの。画像生成APIは使わずAPIコスト0円。
"""

import io
import os
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

import photo_source

WIDTH, HEIGHT = 1280, 670
OUTPUT_DIR = Path(__file__).parent / "docs" / "images"

COLOR_PALETTES = [
    ((30, 41, 59), (15, 23, 42)),      # 紺
    ((76, 29, 149), (49, 10, 101)),    # 紫
    ((6, 78, 59), (4, 47, 46)),        # 深緑
    ((120, 53, 15), (69, 26, 3)),      # 茶
]

FONT_CANDIDATES = [
    os.environ.get("SITE_THUMBNAIL_FONT", ""),
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if path and Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _vertical_gradient(size, top_color, bottom_color):
    img = Image.new("RGB", size, top_color)
    draw = ImageDraw.Draw(img)
    height = size[1]
    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (size[0], y)], fill=(r, g, b))
    return img


def create_thumbnail(title: str, slug: str) -> str:
    """サムネイルを生成し、docs/images/<slug>.png に保存してファイル名を返す"""
    palette = COLOR_PALETTES[hash(title) % len(COLOR_PALETTES)]
    img = _vertical_gradient((WIDTH, HEIGHT), *palette)
    draw = ImageDraw.Draw(img)

    font_size = 68
    font = _load_font(font_size)

    max_chars_per_line = 13
    lines = textwrap.wrap(title, width=max_chars_per_line)
    while len(lines) > 5 and font_size > 36:
        font_size -= 6
        font = _load_font(font_size)
        lines = textwrap.wrap(title, width=max_chars_per_line)

    line_height = int(font_size * 1.4)
    total_height = line_height * len(lines)
    y = (HEIGHT - total_height) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (WIDTH - line_width) // 2
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_height

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{slug}.png"
    img.save(OUTPUT_DIR / filename)
    return filename


def _save_photo_from_url(image_url: str, slug: str) -> str | None:
    """商品画像URL(楽天CDN等)を取得し、幅WIDTHにリサイズしてPNG保存する"""
    try:
        resp = requests.get(image_url, timeout=20)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        if img.width > WIDTH:
            ratio = WIDTH / img.width
            img = img.resize((WIDTH, int(img.height * ratio)))
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{slug}.png"
        img.save(OUTPUT_DIR / filename)
        return filename
    except Exception:
        return None


def create_hero_image(article: dict, photo_query: str | None = None) -> str:
    """記事のヒーロー画像を用意する。優先順位:
    1. 商品紹介記事 → 実際の商品写真(楽天CDN)
    2. 情報系記事 → Pexels(無料写真素材API)で関連写真を検索
    3. 上記が使えない場合 → Pillowでタイトル入りのグラデーション画像を生成(APIコスト0円のフォールバック)
    """
    slug = article["slug"]

    if article.get("type") == "product":
        for item in article.get("affiliate_items", []):
            if item.get("image"):
                filename = _save_photo_from_url(item["image"], slug)
                if filename:
                    return filename

    if photo_query:
        dest = OUTPUT_DIR / f"{slug}.png"
        if photo_source.fetch_photo(photo_query, dest):
            return f"{slug}.png"
        # 記事ごとの検索語で見つからないときは、ジャンル固定の語でもう一度探す(2026-11-24)
        import content_pipeline
        genre_query = next((g.get("photo_query", "") for g in content_pipeline.GENRES
                            if g["id"] == article.get("genre_id")), "")
        if genre_query and genre_query != photo_query and photo_source.fetch_photo(genre_query, dest):
            return f"{slug}.png"

    return create_thumbnail(article["title"], slug)


def create_favicon(letter: str = "暮", color=(180, 83, 9)) -> str:
    """サイトのファビコンを生成する(docs/favicon.png)"""
    size = 256
    img = Image.new("RGB", (size, size), color)
    draw = ImageDraw.Draw(img)
    font = _load_font(int(size * 0.6))
    bbox = draw.textbbox((0, 0), letter, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), letter, font=font, fill=(255, 255, 255))
    SITE_DIR = Path(__file__).parent / "docs"
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    img.save(SITE_DIR / "favicon.png")
    return "favicon.png"
