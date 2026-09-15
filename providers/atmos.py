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
            import datetime as _dt
            expires = _dt.datetime.utcnow() + _dt.timedelta(hours=5, minutes=30)  # Toshkent (UTC+5) + 30 daqiqa
            body = {
                "request_id": order_id,
                "store_id": int(config.ATMOS_STORE_ID),
                "expiration_time": 30,
                "expiration_date": expires.strftime("%Y-%m-%dT%H:%M:%S"),
                "account": order_id,
                "amount": amount_som * 100,  # tiyinda
                "success_url": return_url or "https://example.com/payment/done",
                "items": [{
                    "items_id": "1",
                    "code": "10305001001000000",  # IKPU: dasturiy ta'minot xizmati
                    "name": "Tibbiy Yordamchi obuna",
                    "amount": amount_som * 100,
                    "quantity": 1,
                    "details": {"name": "xizmat_turi", "values": "dasturiy_taminot"},
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
            payment_id = data.get("payment_id")
            invoice_token = data.get("token")
            if payment_id:
                from database import set_order_external_id
                # Ikkalasini ham saqlaymiz (pipe bilan ajratilgan) — checkout/invoice
                # statusini tekshirishda ATMOS aynan qaysi identifikatorni
                # kutishi hali aniq emas, shuning uchun ikkalasini ham sinaymiz.
                set_order_external_id(order_id, f"{payment_id}|{invoice_token or ''}")
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
    xabar yuboradi. Imzoni tekshiramiz, keyin buyurtmani yangilaymiz.

    MUHIM: atmos-pkg kutubxonasining validate_callback_signature funksiyasi
    "invoice" nomli maydonni kutadi, lekin ATMOS, haqiqatda, "account" nomli
    maydonni yuboradi — shuning uchun, kutubxona doim "Noto'g'ri imzo" deb
    rad etar edi. Bu yerda, ATMOS'ning o'zi bergan aniq formulaga ko'ra,
    o'zimizning to'g'ri tekshiruvni yozamiz:
    sign = MD5(store_id + transaction_id + account + amount + api_key)"""
    from atmos.utils import create_callback_response
    import hashlib

    data = await request.json()
    api_key = config.ATMOS_API_KEY or config.ATMOS_CONSUMER_SECRET
    print(f"[ATMOS WEBHOOK KELDI] {data}")

    required = ["store_id", "transaction_id", "account", "amount", "sign"]
    if not all(k in data for k in required):
        print(f"[ATMOS WEBHOOK] Maydon yetishmayapti. Kelgan kalitlar: {list(data.keys())}")
        return create_callback_response(success=False, message="Majburiy maydon yetishmayapti")

    sign_string = f"{data['store_id']}{data['transaction_id']}{data['account']}{data['amount']}{api_key}"
    calculated_sign = hashlib.md5(sign_string.encode()).hexdigest()
    print(f"[ATMOS WEBHOOK] sign_string={sign_string!r} hisoblangan={calculated_sign} kelgan={data['sign']}")

    if data["sign"] != calculated_sign:
        print("[ATMOS WEBHOOK] IMZO MOS KELMADI")
        return create_callback_response(success=False, message="Noto'g'ri imzo")

    order_id = data.get("account")  # bizning order_id shu yerda "account" nomi bilan keladi
    order = get_order(order_id) if order_id else None
    if not order:
        print(f"[ATMOS WEBHOOK] Buyurtma topilmadi: {order_id}")
        return create_callback_response(success=False, message="Buyurtma topilmadi")

    if order["status"] != "paid":
        mark_order_paid(order_id, external_id=str(data.get("transaction_id", "")))
        print(f"[ATMOS WEBHOOK] Buyurtma to'landi deb belgilandi: {order_id}")

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
        import requests as _requests
        raw = order["external_id"] or ""
        parts = raw.split("|")
        payment_id = parts[0] if parts and parts[0] else None
        invoice_token = parts[1] if len(parts) > 1 and parts[1] else None

        with _ScopedAtmosContext():
            client = _get_client()
            bearer = client._ensure_token()
            headers = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}
            store_id = int(config.ATMOS_STORE_ID)

            attempts = []
            if payment_id:
                # Tasdiqlangan, to'g'ri ishlaydigan manzil — birinchi sinaladi
                attempts.append(("/checkout/invoice/get", {"store_id": store_id, "payment_id": int(payment_id)}))
                attempts.append(("/merchant/pay/get", {"store_id": store_id, "transaction_id": int(payment_id)}))
            if invoice_token:
                attempts.append(("/checkout/invoice/get", {"store_id": store_id, "id": invoice_token}))

            for path, body in attempts:
                try:
                    response = _requests.post(f"{client.base_url}{path}", headers=headers, json=body, timeout=20)
                    print(f"[ATMOS CHECK URINISH] {path} {body} → {response.status_code} — {response.text}")
                    data = response.json()
                    block = data.get("status") or data.get("result") or {}
                    code = block.get("code") if isinstance(block, dict) else block
                    # "Topilmadi" xatosi bo'lmasa — bu, to'g'ri manzil bo'lishi mumkin
                    if str(code) != "STPIMS-ERR-061":
                        return data
                except Exception as e:
                    print(f"[ATMOS CHECK URINISH XATOSI] {path} → {type(e).__name__}: {e}")
            return {}

    try:
        info = await asyncio.to_thread(_sync_check)
        # MUHIM: info["status"]["code"]=="0" faqat "ATMOS bu yozuvni topdi" deganidir,
        # HALI TO'LANGANINI bildirmaydi! Haqiqiy to'lov holatini "success"/"state"
        # maydonlaridan tekshiramiz.
        is_paid = bool(info.get("success")) or str(info.get("state", "")).upper() in ("PAID", "CONFIRMED", "COMPLETED", "SUCCESS")
        if is_paid:
            mark_order_paid(order_id, external_id=order.get("external_id"))
            return {"status": "paid"}
    except Exception as e:
        print(f"[ATMOS TEKSHIRISH XATOSI] {type(e).__name__}: {e}")
    return {"status": order["status"]}
