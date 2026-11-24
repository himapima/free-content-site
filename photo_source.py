#!/usr/bin/env python3
"""
記事のヒーロー画像として使う実写真をPexels API(無料)から取得する。
youtube_jidoで発行済みのPEXELS_API_KEYを共有利用する。

取得できない場合(キー未設定・該当写真なし・通信エラー)はNoneを返し、
呼び出し側(content_pipeline.py)がPillow生成のサムネイルにフォールバックする。
"""

import json
import os
import random
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
USED_PHOTOS_FILE = Path(__file__).parent / "used_photos.json"


def _load_used_ids() -> set:
    if not USED_PHOTOS_FILE.exists():
        return set()
    try:
        return set(json.loads(USED_PHOTOS_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_used_id(photo_id) -> None:
    used = _load_used_ids()
    used.add(photo_id)
    USED_PHOTOS_FILE.write_text(json.dumps(sorted(used, key=str), ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_photo(query: str, dest_path: Path) -> bool:
    """queryに合う写真を候補から探し、他の記事でまだ使っていない1枚をdest_pathに保存する。
    同じジャンルのphoto_queryが固定のため、常に上位1件だけを取ると記事間で写真が重複する。
    そのため候補を複数取得し、used_photos.jsonで使用済みIDを避けてランダムに選ぶ。
    成功したらTrue。"""
    if not PEXELS_API_KEY:
        return False
    try:
        resp = requests.get(
            PEXELS_SEARCH_URL,
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": 30, "orientation": "landscape"},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            return False

        used = _load_used_ids()
        candidates = [p for p in photos if p["id"] not in used] or photos
        # 後ろの候補ほど内容から外れるので、まだ使っていない上位6枚から選ぶ(2026-11-24)
        chosen = random.choice(candidates[:6])

        image_url = chosen["src"]["large"]
        img_resp = requests.get(image_url, timeout=20)
        img_resp.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(img_resp.content)
        _save_used_id(chosen["id"])
        return True
    except Exception:
        return False
