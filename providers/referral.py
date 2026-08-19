# -*- coding: utf-8 -*-
"""
Do'stlarni taklif qilish (referral) tizimi.

Har bir foydalanuvchi o'zining shaxsiy kodiga ega. Do'sti shu kodni
kiritsa — ikkalasiga ham bir necha kunlik bepul Premium ('main' tarif)
qo'shiladi (mavjud obuna tizimidan foydalanib, extend_subscription orqali).

Suiiste'mol qilishning oldini olish uchun:
- Bir telefon raqami faqat BIR MARTA (yangi foydalanuvchi sifatida) kod
  kirita oladi (referrals_redeemed jadvalida PRIMARY KEY orqali).
- O'zining kodini o'ziga kirita olmaydi.
"""
import time
import random
import string
import sqlite3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_conn, extend_subscription

router = APIRouter()

REFERRAL_BONUS_DAYS = 3  # har bir muvaffaqiyatli taklif uchun necha kunlik bepul Premium


def _init_referral_tables():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_codes (
                phone TEXT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_redemptions (
                referred_phone TEXT PRIMARY KEY,  -- bitta raqam faqat bir marta kod kirita oladi
                code TEXT NOT NULL,
                referrer_phone TEXT NOT NULL,
                redeemed_at INTEGER NOT NULL
            )
        """)
        conn.commit()


_init_referral_tables()


def _generate_code():
    chars = string.ascii_uppercase.replace('O','').replace('I','') + string.digits.replace('0','').replace('1','')
    return ''.join(random.choice(chars) for _ in range(6))


class CodeRequest(BaseModel):
    phone: str


class RedeemRequest(BaseModel):
    phone: str
    code: str


@router.post("/api/referral/code")
def get_or_create_code(req: CodeRequest):
    phone = req.phone.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Telefon raqami kerak")
    with get_conn() as conn:
        row = conn.execute("SELECT code FROM referral_codes WHERE phone=?", (phone,)).fetchone()
        if row:
            code = row["code"]
        else:
            for _ in range(10):  # to'qnashuv bo'lsa, qayta urinadi
                code = _generate_code()
                try:
                    conn.execute(
                        "INSERT INTO referral_codes (phone, code, created_at) VALUES (?, ?, ?)",
                        (phone, code, int(time.time())),
                    )
                    conn.commit()
                    break
                except sqlite3.IntegrityError:
                    continue
        count = conn.execute(
            "SELECT COUNT(*) as c FROM referral_redemptions WHERE referrer_phone=?", (phone,)
        ).fetchone()["c"]
    return {"code": code, "referral_count": count, "bonus_days": REFERRAL_BONUS_DAYS}


@router.post("/api/referral/redeem")
def redeem_code(req: RedeemRequest):
    phone = req.phone.strip()
    code = req.code.strip().upper()
    if not phone or not code:
        raise HTTPException(status_code=400, detail="Telefon va kod kerak")

    with get_conn() as conn:
        already = conn.execute(
            "SELECT 1 FROM referral_redemptions WHERE referred_phone=?", (phone,)
        ).fetchone()
        if already:
            raise HTTPException(status_code=400, detail="Siz allaqachon bir marta kod kiritgansiz")

        owner = conn.execute("SELECT phone FROM referral_codes WHERE code=?", (code,)).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="Bunday kod topilmadi")
        referrer_phone = owner["phone"]
        if referrer_phone == phone:
            raise HTTPException(status_code=400, detail="O'z kodingizni kirita olmaysiz")

        conn.execute(
            "INSERT INTO referral_redemptions (referred_phone, code, referrer_phone, redeemed_at) VALUES (?, ?, ?, ?)",
            (phone, code, referrer_phone, int(time.time())),
        )
        conn.commit()

    # Ikkalasiga ham bonus kun qo'shiladi (mavjud obuna bo'lsa, davomiyligiga qo'shiladi)
    extend_subscription(referrer_phone, tier="bundle", days=REFERRAL_BONUS_DAYS)
    extend_subscription(phone, tier="bundle", days=REFERRAL_BONUS_DAYS)

    return {"success": True, "bonus_days": REFERRAL_BONUS_DAYS}
