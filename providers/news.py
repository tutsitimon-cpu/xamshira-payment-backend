# -*- coding: utf-8 -*-
"""
Tibbiyot yangiliklari — RSS manbalardan server orqali olib beradi.

Nima uchun bu backend'da (brauzerda emas)?
Ko'pchilik yangiliklar saytlari (jumladan hukumat saytlari) o'z RSS
oqimlarini to'g'ridan-to'g'ri brauzerdan (boshqa domendan) o'qishga
ruxsat bermaydi (bu "CORS" cheklovi deb ataladi). Server orqali o'qisak,
bu cheklov umuman muammo tug'dirmaydi — server har qanday saytdan
ma'lumot ololadi.

Yangi manba qo'shish uchun FEEDS ro'yxatiga shunchaki yangi qator qo'shing.
"""
import time
import feedparser
from fastapi import APIRouter

router = APIRouter()

# Manbalar ro'yxati — xohlagancha qo'shish/o'chirish mumkin.
FEEDS = [
    {"key": "who", "name": "WHO (Jahon sog'liqni saqlash tashkiloti)", "url": "https://www.who.int/rss-feeds/news-english.xml"},
]

_cache = {"data": None, "fetched_at": 0}
CACHE_SECONDS = 60 * 30  # 30 daqiqada bir marta yangilanadi (har so'rovda emas)


def _fetch_all():
    items = []
    for feed in FEEDS:
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries[:15]:
                items.append({
                    "source": feed["name"],
                    "title": getattr(entry, "title", ""),
                    "summary": getattr(entry, "summary", "")[:300] if hasattr(entry, "summary") else "",
                    "link": getattr(entry, "link", ""),
                    "published": getattr(entry, "published", ""),
                })
        except Exception:
            continue  # bitta manba ishlamasa, qolganlari baribir ko'rsatiladi
    return items


@router.get("/api/news")
def get_news():
    now = time.time()
    if _cache["data"] is None or (now - _cache["fetched_at"]) > CACHE_SECONDS:
        _cache["data"] = _fetch_all()
        _cache["fetched_at"] = now
    return {"items": _cache["data"], "cached_at": int(_cache["fetched_at"])}
