# -*- coding: utf-8 -*-
"""
CLICK Shop API integratsiyasi.
Rasmiy hujjat: https://docs.click.uz

CLICK ikkita so'rov yuboradi:
  1) Prepare (action=0)  — to'lov mumkinligini tekshirish
  2) Complete (action=1) — to'lovni yakunlash

Ikkalasida ham CLICK bizga MD5 imzo (sign_string) yuboradi, biz uni
SECRET_KEY yordamida qayta hisoblab, mos kelishini tekshirishimiz shart.
Aks holda, istalgan kishi soxta so'rov yuborib "to'lov qildim" deb aldashi
mumkin bo'lib qoladi.
"""
import hashlib

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from config import CLICK_SECRET_KEY, CLICK_SERVICE_ID
from database import get_order, mark_order_paid, mark_order_canceled

router = APIRouter()

# CLICK xato kodlari (hujjatdan)
ERROR_SUCCESS = 0
ERROR_SIGN_FAILED = -1
ERROR_INVALID_AMOUNT = -2
ERROR_ORDER_NOT_FOUND = -5
ERROR_ALREADY_PAID = -4
ERROR_TRANSACTION_NOT_FOUND = -6
ERROR_ACTION_NOT_FOUND = -3


def _check_signature(data: dict, is_complete: bool) -> bool:
    click_trans_id = str(data.get("click_trans_id", ""))
    service_id = str(data.get("service_id", ""))
    merchant_trans_id = str(data.get("merchant_trans_id", ""))
    amount = str(data.get("amount", ""))
    action = str(data.get("action", ""))
    sign_time = str(data.get("sign_time", ""))
    received_sign = str(data.get("sign_string", ""))

    if is_complete:
        merchant_prepare_id = str(data.get("merchant_prepare_id", ""))
        raw = (click_trans_id + service_id + CLICK_SECRET_KEY + merchant_trans_id
               + merchant_prepare_id + amount + action + sign_time)
    else:
        raw = (click_trans_id + service_id + CLICK_SECRET_KEY + merchant_trans_id
               + amount + action + sign_time)

    expected = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return expected == received_sign


@router.post("/payment/click")
async def click_webhook(request: Request):
    form = await request.form()
    data = dict(form)

    action = str(data.get("action", ""))
    merchant_trans_id = data.get("merchant_trans_id")
    click_trans_id = data.get("click_trans_id")
    amount = data.get("amount")

    order = get_order(merchant_trans_id) if merchant_trans_id else None

    base_response = {
        "click_trans_id": click_trans_id,
        "merchant_trans_id": merchant_trans_id,
    }

    if not _check_signature(data, is_complete=(action == "1")):
        return JSONResponse({**base_response, "error": ERROR_SIGN_FAILED, "error_note": "Sign check failed"})

    if not order:
        return JSONResponse({**base_response, "error": ERROR_ORDER_NOT_FOUND, "error_note": "Order not found"})

    # Miqdorni solishtirish (tiyin -> so'm ekanini eslatma: CLICK so'mda yuboradi)
    try:
        if abs(float(amount) - order["amount_tiyin"] / 100) > 0.01:
            return JSONResponse({**base_response, "error": ERROR_INVALID_AMOUNT, "error_note": "Invalid amount"})
    except (TypeError, ValueError):
        return JSONResponse({**base_response, "error": ERROR_INVALID_AMOUNT, "error_note": "Invalid amount"})

    if action == "0":  # Prepare
        if order["status"] == "paid":
            return JSONResponse({**base_response, "error": ERROR_ALREADY_PAID, "error_note": "Already paid"})
        return JSONResponse({
            **base_response,
            "merchant_prepare_id": order["id"],
            "error": ERROR_SUCCESS,
            "error_note": "Success",
        })

    if action == "1":  # Complete
        error = data.get("error", "0")
        if str(error) != "0":
            mark_order_canceled(order["id"])
            return JSONResponse({
                **base_response,
                "merchant_confirm_id": order["id"],
                "error": ERROR_SUCCESS,
                "error_note": "Canceled by CLICK",
            })
        if order["status"] != "paid":
            mark_order_paid(order["id"], external_id=str(click_trans_id))
        return JSONResponse({
            **base_response,
            "merchant_confirm_id": order["id"],
            "error": ERROR_SUCCESS,
            "error_note": "Success",
        })

    return JSONResponse({**base_response, "error": ERROR_ACTION_NOT_FOUND, "error_note": "Action not found"})


def build_click_pay_url(order_id: str, amount_som: int, return_url: str) -> str:
    """Foydalanuvchini CLICK to'lov sahifasiga yo'naltirish uchun havola."""
    return (
        f"https://my.click.uz/services/pay?service_id={CLICK_SERVICE_ID}"
        f"&merchant_id={CLICK_SERVICE_ID}&amount={amount_som}"
        f"&transaction_param={order_id}&return_url={return_url}"
    )
