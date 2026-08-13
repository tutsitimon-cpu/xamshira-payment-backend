# -*- coding: utf-8 -*-
"""
Ilova ichidan yozilgan xabarlarni (va, agar biriktirilgan bo'lsa, to'lov
chekining skrinshotini) dasturchining shaxsiy Telegram'iga avtomatik
yuborish — foydalanuvchi ilovadan chiqmasdan, to'g'ridan-to'g'ri yordam
so'ray oladi.

Ishlashi uchun Render'da ikkita environment variable kerak:
  - TELEGRAM_BOT_TOKEN — @BotFather'dan olingan token
  - DEVELOPER_CHAT_ID  — xabarlar yuboriladigan Telegram Chat ID
"""
import base64
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config

router = APIRouter()


class SupportMessage(BaseModel):
    message: str
    phone: str = ""
    image_base64: str = ""  # ixtiyoriy — masalan to'lov chekining skrinshoti


@router.post("/api/support/send")
async def send_support_message(req: SupportMessage):
    if not req.message.strip() and not req.image_base64:
        raise HTTPException(status_code=400, detail="Xabar bo'sh bo'lishi mumkin emas")
    if not config.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Xabar yuborish hali sozlanmagan")

    text = "📩 Ilovadan yangi xabar\n\n" + req.message.strip()
    if req.phone.strip():
        text += f"\n\n📞 {req.phone.strip()}"

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            if req.image_base64:
                # Rasm bilan birga — sendPhoto orqali, matn "caption" sifatida
                raw = req.image_base64.split(',')[-1]  # "data:image/...;base64,XXXX" bo'lsa, faqat XXXX qismini olamiz
                image_bytes = base64.b64decode(raw)
                url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
                files = {"photo": ("chek.jpg", image_bytes, "image/jpeg")}
                data = {"chat_id": config.DEVELOPER_CHAT_ID, "caption": text[:1024]}
                resp = await client.post(url, data=data, files=files)
            else:
                url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
                resp = await client.post(url, json={"chat_id": config.DEVELOPER_CHAT_ID, "text": text})
            resp.raise_for_status()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Telegram'ga yuborib bo'lmadi: {str(e)}")

    return {"success": True}

