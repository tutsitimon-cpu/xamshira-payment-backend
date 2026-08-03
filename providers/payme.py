# -*- coding: utf-8 -*-
"""
PAYME Merchant API integratsiyasi (JSON-RPC 2.0).
Rasmiy hujjat: https://developer.help.paycom.uz

PAYME bizning serverimizga bitta URL orqali turli metodlarni yuboradi:
CheckPerformTransaction, CreateTransaction, PerformTransaction,
CancelTransaction, CheckTransaction, GetStatement.

Har bir so'rovda "Authorization: Basic base64(Paycom:SECRET_KEY)" header
kelishi shart — buni tekshirmasak, istalgan kishi bizning "to'lov qabul
qilindi" deb yozishimizga majburlashi mumkin.
"""
import base64
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from config import PAYME_SECRET_KEY
from database import get_conn, get_order, mark_order_paid, mark_order_canceled

router = APIRouter()

# Payme xato kodlari (hujjatdan)
ERR_INVALID_AMOUNT = -31001
ERR_TRANSACTION_NOT_FOUND = -31003
ERR_UNABLE_TO_PERFORM = -31008
ERR_ACCOUNT_NOT_FOUND = -31050
ERR_AUTH_FAILED = -32504


def _check_auth(request: Request) -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        _, key = decoded.split(":", 1)
    except Exception:
        return False
    return key == PAYME_SECRET_KEY


def _rpc_error(id_, code, message):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _rpc_result(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


@router.post("/payment/payme")
async def payme_webhook(request: Request):
    body = await request.json()
    req_id = body.get("id")

    if not _check_auth(request):
        return JSONResponse(_rpc_error(req_id, ERR_AUTH_FAILED, "Authorization required"))

    method = body.get("method")
    params = body.get("params", {})

    if method == "CheckPerformTransaction":
        return _check_perform(req_id, params)
    if method == "CreateTransaction":
        return _create_transaction(req_id, params)
    if method == "PerformTransaction":
        return _perform_transaction(req_id, params)
    if method == "CancelTransaction":
        return _cancel_transaction(req_id, params)
    if method == "CheckTransaction":
        return _check_transaction(req_id, params)
    if method == "GetStatement":
        return JSONResponse(_rpc_result(req_id, {"transactions": []}))

    return JSONResponse(_rpc_error(req_id, -32601, "Method not found"))


def _find_order_by_account(params):
    account = params.get("account", {})
    order_id = account.get("order_id") or account.get("key")
    if not order_id:
        return None
    return get_order(order_id)


def _check_perform(req_id, params):
    order = _find_order_by_account(params)
    if not order:
        return JSONResponse(_rpc_error(req_id, ERR_ACCOUNT_NOT_FOUND, "Order not found"))
    if int(params.get("amount", 0)) != int(order["amount_tiyin"]):
        return JSONResponse(_rpc_error(req_id, ERR_INVALID_AMOUNT, "Invalid amount"))
    return JSONResponse(_rpc_result(req_id, {"allow": True}))


def _create_transaction(req_id, params):
    order = _find_order_by_account(params)
    if not order:
        return JSONResponse(_rpc_error(req_id, ERR_ACCOUNT_NOT_FOUND, "Order not found"))
    if int(params.get("amount", 0)) != int(order["amount_tiyin"]):
        return JSONResponse(_rpc_error(req_id, ERR_INVALID_AMOUNT, "Invalid amount"))

    payme_trans_id = params["id"]
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM orders WHERE external_id=?", (payme_trans_id,)
        ).fetchone()
        if existing and existing["status"] == "canceled":
            return JSONResponse(_rpc_error(req_id, ERR_UNABLE_TO_PERFORM, "Transaction canceled"))
        conn.execute(
            "UPDATE orders SET external_id=?, provider='payme' WHERE id=?",
            (payme_trans_id, order["id"]),
        )
        conn.commit()

    return JSONResponse(_rpc_result(req_id, {
        "create_time": int(time.time() * 1000),
        "transaction": order["id"],
        "state": 1,
    }))


def _perform_transaction(req_id, params):
    payme_trans_id = params["id"]
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE external_id=?", (payme_trans_id,)).fetchone()
    if not row:
        return JSONResponse(_rpc_error(req_id, ERR_TRANSACTION_NOT_FOUND, "Transaction not found"))

    if row["status"] != "paid":
        mark_order_paid(row["id"], external_id=payme_trans_id)

    return JSONResponse(_rpc_result(req_id, {
        "transaction": row["id"],
        "perform_time": int(time.time() * 1000),
        "state": 2,
    }))


def _cancel_transaction(req_id, params):
    payme_trans_id = params["id"]
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE external_id=?", (payme_trans_id,)).fetchone()
    if not row:
        return JSONResponse(_rpc_error(req_id, ERR_TRANSACTION_NOT_FOUND, "Transaction not found"))

    mark_order_canceled(row["id"])
    return JSONResponse(_rpc_result(req_id, {
        "transaction": row["id"],
        "cancel_time": int(time.time() * 1000),
        "state": -1,
    }))


def _check_transaction(req_id, params):
    payme_trans_id = params["id"]
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE external_id=?", (payme_trans_id,)).fetchone()
    if not row:
        return JSONResponse(_rpc_error(req_id, ERR_TRANSACTION_NOT_FOUND, "Transaction not found"))

    state = 2 if row["status"] == "paid" else (-1 if row["status"] == "canceled" else 1)
    return JSONResponse(_rpc_result(req_id, {
        "create_time": int(row["created_at"] * 1000),
        "perform_time": int(row["paid_at"] * 1000) if row["paid_at"] else 0,
        "cancel_time": 0,
        "transaction": row["id"],
        "state": state,
    }))


def build_payme_pay_url(order_id: str, amount_tiyin: int) -> str:
    """Foydalanuvchini Payme to'lov sahifasiga yo'naltirish uchun havola."""
    from config import PAYME_MERCHANT_ID
    params = f"m={PAYME_MERCHANT_ID};ac.order_id={order_id};a={amount_tiyin}"
    encoded = base64.b64encode(params.encode("utf-8")).decode("utf-8")
    return f"https://checkout.paycom.uz/{encoded}"
