# -*- coding: utf-8 -*-
"""
ATMOS to'lov integratsiyasi — Click/Payme/Uzcard/Humo/Visa/Mastercard'ni
yagona API orqali qamrab oladigan agregator.

Ishlash tartibi:
  1. Foydalanuvchi tarif tanlaydi → /api/subscribe/init chaqiriladi →
     shu yerda ATMOS'da tranzaksiya yaratiladi → to'lov sahifasi havolasi
     qaytariladi (checkout.pays.uz).
  2. Foydalanuvchi shu sahifada to'laydi.
  3. ATMOS bizning /api/atmos/webhook manzilimizga xabar yuboradi →
     imzo tekshiriladi → order "paid" deb belgilanadi → obuna uzaytiriladi.

ATMOS_CONSUMER_KEY, ATMOS_CONSUMER_SECRET, ATMOS_STORE_ID — Render
environment variable sifatida kiritiladi. Hozircha SANDBOX (sinov)
muhitida ishlaydi — production kalitlar kelgach, config.py'da
ATMOS_TEST_MODE ni False qilib almashtiriladi.

Agar FIXIE_URL berilgan bo'lsa, barcha ATMOS so'rovlari shu statik IP
proksi orqali yuboriladi (ATMOS whitelist qilgan IP'lardan chiqishi uchun).
"""
import os
import asyncio
from fastapi import APIRouter, HTTPException, Request

import config
from database import get_order, mark_order_paid, mark_order_canceled

router = APIRouter()

_client = None


def _get_client():
    """AtmosClient'ni faqat bir marta yaratadi (token keshini saqlab qolish
    uchun). Proksi bu yerda O'RNATILMAYDI — har bir chaqiruv atrofida,
    faqat shu chaqiruv davomida vaqtincha o'rnatiladi (pastga qarang),
    shunda boshqa so'rovlarga (masalan /health, Gemini, Telegram) ta'sir
    qilmaydi."""
    global _client
    if _client is not None:
        return _client

    from atmos import AtmosClient

    _client = AtmosClient(
        consumer_key=config.ATMOS_CONSUMER_KEY,
        consumer_secret=config.ATMOS_CONSUMER_SECRET,
        store_id=config.ATMOS_STORE_ID,
        test_mode=False,
        language="uz",
    )
    # Kutubxonaning ichki manzili ("partner.atmos.uz") ESKIRGAN — ATMOS
    # o'zi tasdiqlagan HOZIRGI, TO'G'RI manzil bilan almashtiramiz:
    _client.base_url = "https://apigw.atmos.uz"
    return _client


class _ScopedAtmosContext:
    """Ikkita narsani FAQAT shu 'with' bloki davomida sozlaydi, keyin
    darhol avvalgi holatga qaytaradi — shunda boshqa (parallel yoki
    keyingi) so'rovlarga (masalan /health, Gemini, Telegram) ta'sir
    qilmaydi:
      1. Fixie proksisi (ATMOS whitelist qilgan IP'dan chiqish uchun)
      2. So'rov kutish vaqti — kutubxonada 30 soniya qattiq yozilgan,
         ATMOS esa buni 120 soniyagacha oshirishni tavsiya qildi
         (ba'zan javob sekinroq kelishi mumkin ekan)."""
    def __enter__(self):
        self._prev_https = os.environ.get("HTTPS_PROXY")
        self._prev_http = os.environ.get("HTTP_PROXY")
        if config.FIXIE_URL:
            os.environ["HTTPS_PROXY"] = config.FIXIE_URL
            os.environ["HTTP_PROXY"] = config.FIXIE_URL

        import requests
        self._orig_post = requests.post
        def _patched_post(*args, **kwargs):
            kwargs["timeout"] = 120  # kutubxonaning 30s qattiq belgilangan qiymatini almashtiramiz
            return self._orig_post(*args, **kwargs)
        requests.post = _patched_post

        return self

    def __exit__(self, *exc):
        import requests
        requests.post = self._orig_post
        for key, prev in (("HTTPS_PROXY", self._prev_https), ("HTTP_PROXY", self._prev_http)):
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev


async def build_atmos_pay_url(order_id: str, amount_som: int, return_url: str = "") -> str:
    """/api/subscribe/init ichidan chaqiriladi — click/payme/paynet bilan
    bir xil pattern: buyurtma ID + summa (so'mda) beriladi, to'lov sahifasi
    havolasi qaytariladi."""
    if not config.ATMOS_CONSUMER_KEY or not config.ATMOS_CONSUMER_SECRET or not config.ATMOS_STORE_ID:
        return ""  # hali sozlanmagan — ilova bu tugmani ko'rsatmasligi kerak

    def _sync_create():
        with _ScopedAtmosContext():
            client = _get_client()
            amount_tiyin = amount_som * 100
            transaction = client.create_transaction(amount=amount_tiyin, account=order_id)
        # get_*_payment_page_url — bu haqiqiy tarmoq so'rovi emas, faqat URL
        # matnini quradi, shuning uchun proksi doirasidan tashqarida bo'lishi mumkin
        if config.ATMOS_TEST_MODE:
            return client.get_test_payment_page_url(transaction.transaction_id, redirect_url=return_url)
        return client.get_payment_page_url(transaction.transaction_id, redirect_url=return_url)

    try:
        return await asyncio.to_thread(_sync_create)
    except Exception as e:
        import traceback
        print(f"[ATMOS XATOSI] {type(e).__name__}: {e}")
        traceback.print_exc()
        return ""  # ATMOS vaqtincha ishlamasa, ilova shunchaki bu tugmani ko'rsatmaydi


@router.post("/api/atmos/webhook")
async def atmos_webhook(request: Request):
    """ATMOS to'lov muvaffaqiyatli/muvaffaqiyatsiz bo'lganda shu yerga
    xabar yuboradi. Imzoni tekshiramiz, keyin buyurtmani yangilaymiz."""
    from atmos.utils import validate_callback_signature, create_callback_response

    data = await request.json()
    api_key = config.ATMOS_CONSUMER_SECRET  # webhook imzosi uchun ham shu kalit ishlatiladi

    if not validate_callback_signature(data, api_key):
        return create_callback_response(success=False, message="Noto'g'ri imzo")

    order_id = data.get("invoice")  # bizning order_id shu yerda "invoice" nomi bilan keladi
    order = get_order(order_id) if order_id else None
    if not order:
        return create_callback_response(success=False, message="Buyurtma topilmadi")

    if order["status"] != "paid":
        mark_order_paid(order_id, external_id=str(data.get("transaction_id", "")))

    return create_callback_response(success=True)


@router.get("/api/atmos/check/{order_id}")
async def atmos_check(order_id: str):
    """Ilova "To'lovni tekshirish" tugmasi bosilganda, webhook hali
    kelmagan bo'lsa ham, ATMOS'dan to'g'ridan-to'g'ri holatni so'raydi."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if order["status"] == "paid":
        return {"status": "paid"}
    if not order.get("external_id"):
        return {"status": order["status"]}  # ATMOS tranzaksiya ID hali yo'q

    def _sync_check():
        with _ScopedAtmosContext():
            client = _get_client()
            return client.get_transaction_info(int(order["external_id"]))

    try:
        info = await asyncio.to_thread(_sync_check)
        if info.get("status") in (1, "1", "paid", "success"):
            mark_order_paid(order_id, external_id=order.get("external_id"))
            return {"status": "paid"}
    except Exception as e:
        print(f"[ATMOS TEKSHIRISH XATOSI] {type(e).__name__}: {e}")
    return {"status": order["status"]}
