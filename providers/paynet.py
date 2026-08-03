# -*- coding: utf-8 -*-
"""
PAYNET integratsiyasi.

MUHIM ESLATMA: Paynet.uz'ning to'lov havolasi formati oddiy va ma'lum
(pastda), lekin ularning webhook (to'lov tasdiqlash) so'rovi qanday
imzolanishini ko'rsatuvchi ochiq hujjat topilmadi — bu odatda merchant
sifatida ro'yxatdan o'tgandan so'ng, Paynet administratori tomonidan
alohida beriladi (odatda shaxsiy hisobingizga ulanganda PDF/ Word
ko'rinishida yuboriladi).

Shuning uchun bu faylda:
  1) To'lov havolasini yaratish qismi — TO'LIQ ishlaydi.
  2) Webhook qabul qilish qismi — TODO skelet, Paynet'dan hujjat kelgach
     to'ldirish kerak (odatda ular ham "amount" va "order_id" solishtirish,
     imzoni tekshirish so'rashadi, xuddi Click/Payme kabi).
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from config import PAYNET_MERCHANT_ID
from database import get_order, mark_order_paid

router = APIRouter()


def build_paynet_pay_url(order_id: str, amount_tiyin: int) -> str:
    """Foydalanuvchini Paynet to'lov sahifasiga yo'naltirish uchun havola.
    Format: https://app.paynet.uz/?m={merchant_id}&c={payment_id}&a={amount_tiyin}
    """
    return f"https://app.paynet.uz/?m={PAYNET_MERCHANT_ID}&c={order_id}&a={amount_tiyin}"


@router.post("/payment/paynet")
async def paynet_webhook(request: Request):
    """
    TODO: Paynet merchant hisobingizni ochganingizda ular bergan hujjatga
    qarab shu funksiyani to'ldiring — odatda quyidagilarni tekshirish kerak
    bo'ladi:
      1) So'rovni Paynet yuborganini tasdiqlovchi imzo/token
      2) order_id (bizning 'c' parametrimiz) haqiqatan mavjudligi
      3) amount to'g'ri kelishi
    Shundan keyin mark_order_paid(order_id, external_id=...) chaqiring —
    xuddi Click/Payme handlerlarida qilingani kabi.
    """
    data = await request.json()
    order_id = data.get("order_id") or data.get("c")
    order = get_order(order_id) if order_id else None

    if not order:
        return JSONResponse({"status": "error", "message": "Order not found"}, status_code=404)

    # ⚠️ Hozircha imzo tekshiruvi yo'q — Paynet hujjati kelgach shu yerga qo'shing.
    mark_order_paid(order["id"], external_id=str(data.get("transaction_id", "")))
    return JSONResponse({"status": "ok"})
