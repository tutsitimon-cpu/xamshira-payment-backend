# -*- coding: utf-8 -*-
"""
AI Yordamchi — tibbiyot xodimlari uchun AI yordamchi.

Ikkita AI provayderini qo'llab-quvvatlaydi:
  - "gemini" (standart)   — Google'ning BEPUL tarifi (aistudio.google.com'dan
                             kalit olinadi, bank kartasi kerak emas)
  - "anthropic"           — Claude (pullik, agar kelajakda sifatni oshirish
                             kerak bo'lsa, config.py'da AI_PROVIDER="anthropic"
                             qilib almashtirish mumkin)

Qaysi birini ishlatishni config.py'dagi AI_PROVIDER o'zgaruvchisi belgilaydi.
So'rovlar to'g'ridan-to'g'ri ilovadan emas, shu backend orqali yuboriladi —
chunki haqiqiy API kaliti mijoz tarafida (ilovada) hech qachon saqlanmasligi
kerak (xavfsizlik uchun).
"""
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

import config

router = APIRouter()

SYSTEM_PROMPT = """Siz "Tibbiy Yordamchi" ilovasidagi AI yordamchisiz — O'zbekistondagi \
hamshiralar, vrachlar va boshqa tibbiyot xodimlari uchun yordamchi.

Qoidalar:
- Foydalanuvchi yozgan tilda javob bering (o'zbek, rus yoki ingliz).
- Tibbiy savollarga aniq, ishonchli va tushunarli javob bering.
- Murakkab yoki xavfli klinik qarorlar uchun har doim "bu yordamchi ma'lumot, \
yakuniy qarorni malakali shifokor/hamshira o'z bilimiga tayanib qabul qilishi \
kerak" kabi eslatma qo'shing.
- Dori dozalari yoki xavfli protseduralar haqida so'ralganda ehtiyotkor bo'ling, \
umumiy ma'lumot bering, lekin aniq bemorga xos qaror qabul qilmang.
- Javoblaringiz qisqa va amaliy bo'lsin — telefon ekranida o'qiladi."""


class ChatMessage(BaseModel):
    role: str  # "user" yoki "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


async def _call_gemini(messages):
    if not config.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="AI Yordamchi hali sozlanmagan (GEMINI_API_KEY yo'q)")

    contents = [
        {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
        for m in messages
    ]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
                json={
                    "contents": contents,
                    "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "generationConfig": {"maxOutputTokens": 1024},
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Gemini xatosi: {e.response.text[:200]}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Gemini'ga ulanib bo'lmadi: {str(e)}")

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return "⚠ Gemini'dan javob olinmadi (bo'sh natija)."


async def _call_anthropic(messages):
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="AI Yordamchi hali sozlanmagan (ANTHROPIC_API_KEY yo'q)")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": config.AI_MODEL,
                    "max_tokens": 1024,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"AI xizmatida xato: {e.response.text[:200]}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AI xizmatiga ulanib bo'lmadi: {str(e)}")

    reply_text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            reply_text += block.get("text", "")
    return reply_text


@router.post("/api/ai-chat")
async def ai_chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="Xabar yo'q")

    if config.AI_PROVIDER == "anthropic":
        reply_text = await _call_anthropic(req.messages)
    else:
        reply_text = await _call_gemini(req.messages)

    return {"reply": reply_text}
