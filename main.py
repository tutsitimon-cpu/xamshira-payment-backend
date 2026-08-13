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
from database import init_db, create_order, get_subscription_status, TIER_PRICES_SOM
from providers.click import router as click_router, build_click_pay_url
from providers.payme import router as payme_router, build_payme_pay_url
from providers.paynet import router as paynet_router, build_paynet_pay_url
from providers.news import router as news_router
from providers.ai_assistant import router as ai_router
from providers.referral import router as referral_router
from providers.support import router as support_router

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
app.include_router(news_router)
app.include_router(ai_router)
app.include_router(referral_router)
app.include_router(support_router)


@app.on_event("startup")
def _startup():
    init_db()


class InitSubscriptionRequest(BaseModel):
    phone: str  # masalan: "998901234567"
    tier: str = "main"  # "main" (35k) | "ai" (20k) | "bundle" (55k)
    return_url: str = "https://example.com/payment/done"


@app.post("/api/subscribe/init")
def init_subscription(payload: InitSubscriptionRequest):
    """
    Foydalanuvchi tarif tanlab "Obuna bo'lish" tugmasini bosganda ilova shu
    endpointga murojaat qiladi. Javobida uchala to'lov tizimi uchun ham
    tayyor havola qaytadi — ilova foydalanuvchiga 3 ta tugma (Click / Payme /
    Paynet) ko'rsatadi, u qaysinisini tanlasa o'sha havolaga o'tadi.
    """
    tier = payload.tier if payload.tier in TIER_PRICES_SOM else "main"
    amount_som = TIER_PRICES_SOM[tier]
    amount_tiyin = amount_som * 100
    order_id = create_order(payload.phone, amount_tiyin, provider=None, tier=tier)

    return {
        "order_id": order_id,
        "tier": tier,
        "amount_som": amount_som,
        "subscription_days": SUBSCRIPTION_DAYS,
        "pay_urls": {
            "click": build_click_pay_url(order_id, amount_som, payload.return_url),
            "payme": build_payme_pay_url(order_id, amount_tiyin),
            "paynet": build_paynet_pay_url(order_id, amount_tiyin),
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
