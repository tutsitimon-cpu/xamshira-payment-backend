# -*- coding: utf-8 -*-
"""
Tibbiyot yangiliklari — RSS manbalardan server orqali olib beradi, va
xohlasa AI (Gemini) orqali tarjima qilib beradi.

Nima uchun bu backend'da (brauzerda emas)?
Ko'pchilik yangiliklar saytlari (jumladan hukumat saytlari) o'z RSS
oqimlarini to'g'ridan-to'g'ri brauzerdan (boshqa domendan) o'qishga
ruxsat bermaydi (bu "CORS" cheklovi deb ataladi). Server orqali o'qisak,
bu cheklov umuman muammo tug'dirmaydi — server har qanday saytdan
ma'lumot ololadi.

Muhim: RSS manbaga so'rov qat'iy vaqt chegarasi (timeout) bilan yuboriladi.
Aks holda, agar manba sekin/ishlamay qolsa, butun so'rov osilib qolib,
foydalanuvchi ilovasida "Failed to fetch" xatosiga olib kelishi mumkin edi
(bu — avval haqiqatan ham yuz bergan muammo).

Tarjima — bepul Gemini orqali, va faqat 30 daqiqada BIR MARTA qilinadi
(har bir foydalanuvchi uchun emas, umumiy keshga), shuning uchun kunlik
bepul limitdan juda oz qismi sarflanadi.

Yangi manba qo'shish uchun FEEDS ro'yxatiga shunchaki yangi qator qo'shing.
"""
import time
import json
import httpx
import feedparser
from fastapi import APIRouter

import config

router = APIRouter()

# Manbalar ro'yxati — xohlagancha qo'shish/o'chirish mumkin.
FEEDS = [
    {"key": "who", "name": "WHO (Jahon sog'liqni saqlash tashkiloti)", "url": "https://www.who.int/rss-feeds/news-english.xml"},
]

FETCH_TIMEOUT_SECONDS = 6  # bitta manba shundan ortiq javob bermasa, tashlab ketiladi
TRANSLATE_TIMEOUT_SECONDS = 15  # tarjima ham qat'iy vaqt chegarasi bilan

_cache = {"data": None, "fetched_at": 0}
_translated_cache = {}  # {"uz": {"data":[...], "fetched_at":...}, "ru": {...}}
CACHE_SECONDS = 60 * 30  # 30 daqiqada bir marta yangilanadi (har so'rovda emas)

LANG_NAMES = {"uz": "o'zbek (lotin yozuvida, krill emas)", "ru": "rus"}


def _fetch_all():
    items = []
    for feed in FEEDS:
        try:
            resp = httpx.get(feed["url"], timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)  # endi tarmoqqa chiqmaydi, faqat matnni o'qiydi
            for entry in parsed.entries[:15]:
                items.append({
                    "source": feed["name"],
                    "title": getattr(entry, "title", ""),
                    "summary": getattr(entry, "summary", "")[:300] if hasattr(entry, "summary") else "",
                    "link": getattr(entry, "link", ""),
                    "published": getattr(entry, "published", ""),
                })
        except Exception:
            continue  # bitta manba ishlamasa (yoki vaqt tugasa), qolganlari baribir ko'rsatiladi
    return items


async def _translate_items(items, lang):
    if not config.GEMINI_API_KEY or not items:
        return items  # kalit yo'q yoki bo'sh — asl (inglizcha) holida qaytariladi

    lang_name = LANG_NAMES.get(lang, lang)
    payload_for_ai = [{"i": idx, "title": it["title"], "summary": it["summary"]} for idx, it in enumerate(items)]
    prompt = (
        f"Quyidagi yangiliklar ro'yxatidagi har bir \"title\" va \"summary\" matnini {lang_name} tiliga tarjima qil. "
        f"Faqat JSON massiv qaytar, boshqa hech qanday matn yozma (izoh, tushuntirish shart emas). "
        f"Har bir element: {{\"i\": <raqam>, \"title\": \"<tarjima>\", \"summary\": \"<tarjima>\"}}.\n\n"
        f"Yangiliklar: {json.dumps(payload_for_ai, ensure_ascii=False)}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    try:
        async with httpx.AsyncClient(timeout=TRANSLATE_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 4096},
                },
            )
            resp.raise_for_status()
            data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        translated_list = json.loads(raw_text)
        translated_by_index = {t["i"]: t for t in translated_list if "i" in t}

        result = []
        for idx, it in enumerate(items):
            t = translated_by_index.get(idx)
            new_item = dict(it)
            if t:
                new_item["title"] = t.get("title", it["title"])
                new_item["summary"] = t.get("summary", it["summary"])
            result.append(new_item)
        return result
    except Exception:
        return items  # tarjima muvaffaqiyatsiz bo'lsa, asl (inglizcha) matn ko'rsatiladi


@router.get("/api/news")
async def get_news(lang: str = "en"):
    now = time.time()
    if _cache["data"] is None or (now - _cache["fetched_at"]) > CACHE_SECONDS:
        _cache["data"] = _fetch_all()
        _cache["fetched_at"] = now
        _translated_cache.clear()  # manba yangilanganda, eski tarjimalar ham eskirgan hisoblanadi

    if lang not in LANG_NAMES:
        return {"items": _cache["data"], "cached_at": int(_cache["fetched_at"])}

    cached_t = _translated_cache.get(lang)
    if cached_t is None or cached_t["fetched_at"] != _cache["fetched_at"]:
        translated = await _translate_items(_cache["data"], lang)
        _translated_cache[lang] = {"data": translated, "fetched_at": _cache["fetched_at"]}
        cached_t = _translated_cache[lang]

    return {"items": cached_t["data"], "cached_at": int(_cache["fetched_at"])}
