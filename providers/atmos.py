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
    import time as _time
    import requests as _requests
    from atmos.exceptions import AtmosAuthError

    def _fixed_get_token(self):
        """ATMOS'ning YANGI apigw.atmos.uz manzili uchun, bir nechta keng
        tarqalgan autentifikatsiya usulini KETMA-KET sinaymiz — chunki
        aniq qaysi format kerakligi hali to'liq tasdiqlanmagan. Birinchi
        muvaffaqiyatli bo'lgani ishlatiladi; barchasi muvaffaqiyatsiz
        bo'lsa, ENG OXIRGI xato (batafsil) ko'rsatiladi."""
        token_url = f"{self.base_url}/token"
        auth_basic = self._get_auth_header()
        attempts = [
            # 1) Basic Auth header + grant_type so'rov satrida (ATMOS aytgan format)
            {"params": {"grant_type": "client_credentials"},
             "headers": {"Authorization": auth_basic}},
            # 2) client_id/client_secret HAM so'rov satrida (Kong/ko'p api-gateway uslubi)
            {"params": {"grant_type": "client_credentials",
                        "client_id": self.consumer_key,
                        "client_secret": self.consumer_secret}},
            # 3) client_id/client_secret so'rov TANASIDA (form), grant_type esa satrida
            {"params": {"grant_type": "client_credentials"},
             "data": {"client_id": self.consumer_key, "client_secret": self.consumer_secret}},
            # 4) Basic Auth + client_id HAM so'rov satrida qo'shilgan
            {"params": {"grant_type": "client_credentials", "client_id": self.consumer_key},
             "headers": {"Authorization": auth_basic}},
        ]
        last_error = None
        for i, attempt in enumerate(attempts, 1):
            try:
                response = _requests.post(token_url, timeout=30, **attempt)
                if response.status_code == 200:
                    token_data = response.json()
                    self.access_token = token_data["access_token"]
                    self.token_expires_at = _time.time() + token_data["expires_in"] - 60
                    print(f"[ATMOS] Muvaffaqiyatli usul: #{i} — {attempt}")
                    return self.access_token
                last_error = f"Urinish #{i} ({list(attempt.keys())}): {response.status_code} — {response.text}"
                print(f"[ATMOS TOKEN URINISH XATOSI] {last_error}")
            except Exception as e:
                last_error = f"Urinish #{i}: {type(e).__name__}: {e}"
                print(f"[ATMOS TOKEN URINISH XATOSI] {last_error}")
        raise AtmosAuthError(f"Barcha 4 usul ham muvaffaqiyatsiz. Oxirgisi: {last_error}")

    AtmosClient._get_token = _fixed_get_token

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
    havolasi qaytariladi.

    ATMOS'ning rasmiy hujjatlariga ko'ra (docs.atmos.uz), to'g'ri usul —
    kutubxonaning oddiy create_transaction + URL-qurish usuli EMAS, balki
    alohida /checkout/invoice/create so'rovi, bu esa tayyor, ishlaydigan
    checkout havolasini o'zi qaytaradi."""
    if not config.ATMOS_CONSUMER_KEY or not config.ATMOS_CONSUMER_SECRET or not config.ATMOS_STORE_ID:
        return ""  # hali sozlanmagan — ilova bu tugmani ko'rsatmasligi kerak

    def _sync_create():
        import requests as _requests
        with _ScopedAtmosContext():
            client = _get_client()  # token olish/yangilashni o'zi boshqaradi
            token = client._ensure_token()
            body = {
                "request_id": order_id,
                "store_id": int(config.ATMOS_STORE_ID),
                "account": order_id,
                "amount": amount_som * 100,  # tiyinda
                "success_url": return_url or "https://example.com/payment/done",
                "items": [{
                    "items_id": "1",
                    "code": "10305001001000000",  # IKPU: dasturiy ta'minot xizmati
                    "name": "Tibbiy Yordamchi obuna",
                    "amount": amount_som * 100,
                    "quantity": 1,
                }],
            }
            response = _requests.post(
                f"{client.base_url}/checkout/invoice/create",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            )
            print(f"[ATMOS INVOICE STATUS] {response.status_code} — {response.text}")
            response.raise_for_status()
            data = response.json()
            return data.get("url") or data.get("payload", {}).get("url", "")

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
