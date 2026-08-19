# -*- coding: utf-8 -*-
"""
Xamshira Test — obuna va to'lov backend serveri.

Ishga tushirish (lokal sinov uchun):
    pip install -r requirements.txt
    cp .env.example .env      # so'ng .env faylini haqiqiy kalitlar bilan to'ldiring
    uvicorn main:app --reload --port 8000

Productionda (haqiqiy serverda) nginx + systemd orqali ishga tushiriladi —
README.md faylida to'liq qo'llanma bor.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import SUBSCRIPTION_DAYS
from database import init_db, create_order, get_subscription_status, get_tier_price
from providers.click import router as click_router, build_click_pay_url
from providers.payme import router as payme_router, build_payme_pay_url
from providers.paynet import router as paynet_router, build_paynet_pay_url
from providers.atmos import router as atmos_router, build_atmos_pay_url
from providers.news import router as news_router
from providers.ai_assistant import router as ai_router
from providers.referral import router as referral_router
from providers.support import router as support_router
from providers.admin import router as admin_router

app = FastAPI(title="Xamshira Test — Obuna API")

# Ilova (APK/veb) boshqa domendan so'rov yuborishi mumkin bo'lgani uchun CORS ochiq.
# Productionda allow_origins ni o'z domeningiz bilan cheklashni unutmang.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(click_router)
app.include_router(payme_router)
app.include_router(paynet_router)
app.include_router(atmos_router)
app.include_router(news_router)
app.include_router(ai_router)
app.include_router(referral_router)
app.include_router(support_router)
app.include_router(admin_router)


@app.on_event("startup")
def _startup():
    init_db()


class InitSubscriptionRequest(BaseModel):
    phone: str  # masalan: "998901234567"
    tier: str = "toifa"  # "toifa" (25k/50k) | "specialty" (50k/100k) | "ai" (20k) | "bundle" (110k/220k)
    group: str = "orta"  # "orta" (hamshira) | "vrach" (shifokor) — narxni belgilaydi
    specialty_key: str = ""  # masalan "hamshiralik-ishi" — 'toifa'/'specialty' tarifi uchun kerak
    toifa_key: str = ""  # masalan "1-toifa" — faqat 'toifa' tarifi uchun kerak
    return_url: str = "https://example.com/payment/done"


@app.post("/api/subscribe/init")
async def init_subscription(payload: InitSubscriptionRequest):
    """
    Foydalanuvchi tarif tanlab "Obuna bo'lish" tugmasini bosganda ilova shu
    endpointga murojaat qiladi. Javobida barcha to'lov tizimlari uchun
    tayyor havola qaytadi.
    """
    tier = payload.tier if payload.tier in ("toifa", "specialty", "ai", "bundle") else "toifa"
    group = payload.group if payload.group in ("orta", "vrach") else "orta"
    amount_som = get_tier_price(tier, group)
    amount_tiyin = amount_som * 100
    order_id = create_order(
        payload.phone, amount_tiyin, provider=None, tier=tier, group_name=group,
        specialty_key=payload.specialty_key or None, toifa_key=payload.toifa_key or None,
    )

    atmos_url = await build_atmos_pay_url(order_id, amount_som, payload.return_url)

    return {
        "order_id": order_id,
        "tier": tier,
        "group": group,
        "amount_som": amount_som,
        "subscription_days": SUBSCRIPTION_DAYS,
        "pay_urls": {
            "click": build_click_pay_url(order_id, amount_som, payload.return_url),
            "payme": build_payme_pay_url(order_id, amount_tiyin),
            "paynet": build_paynet_pay_url(order_id, amount_tiyin),
            "atmos": atmos_url,  # bo'sh bo'lsa, ilova bu tugmani ko'rsatmaydi (ATMOS hali sozlanmagan)
        },
    }


@app.get("/api/subscription/status")
def subscription_status(phone: str):
    """Ilova har safar ochilganda shu yerdan foydalanuvchining obunasi
    faolmi-yo'qmi tekshiradi (freemium cheklovini shunga qarab qo'yadi)."""
    return get_subscription_status(phone)


@app.get("/health")
def health():
    return {"status": "ok"}
