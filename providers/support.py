# -*- coding: utf-8 -*-
"""
Ilova ichidan yozilgan xabarlarni dasturchining shaxsiy Telegram'iga
avtomatik yuborish — foydalanuvchi ilovadan chiqmasdan, to'g'ridan-to'g'ri
yordam so'ray oladi.

Ishlashi uchun Render'da ikkita environment variable kerak:
  - TELEGRAM_BOT_TOKEN — @BotFather'dan olingan token
  - DEVELOPER_CHAT_ID  — xabarlar yuboriladigan Telegram Chat ID
"""
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config

router = APIRouter()


class SupportMessage(BaseModel):
    message: str
    phone: str = ""


@router.post("/api/support/send")
async def send_support_message(req: SupportMessage):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Xabar bo'sh bo'lishi mumkin emas")
    if not config.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Xabar yuborish hali sozlanmagan")

    text = "📩 Ilovadan yangi xabar\n\n" + req.message.strip()
    if req.phone.strip():
        text += f"\n\n📞 {req.phone.strip()}"

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, json={"chat_id": config.DEVELOPER_CHAT_ID, "text": text})
            resp.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Telegram'ga yuborib bo'lmadi: {str(e)}")

    return {"success": True}
