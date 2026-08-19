# -*- coding: utf-8 -*-
"""
Admin statistika — nechta odam ilovaga ulanganini, nechta kishi qaysi
tarifni (asosiy/AI/hammasi) sotib olganini ko'rish uchun.

Ikkita usul orqali "sotib olish" hisoblanadi:
  1. Qo'lda faollashtirish kodi kiritilganda — ilova shu yerga xabar beradi
  2. Avtomatik to'lov (Click/Payme/Paynet) orqali — bu allaqachon
     `subscriptions` jadvaliga yoziladi (database.py)

Statistikani ko'rish uchun brauzerda oching:
  https://xamshira-backend.onrender.com/api/admin/stats?key=SIZNING_MAXFIY_KALIT

Maxfiy kalitni Render'da ADMIN_KEY nomi bilan environment variable
sifatida qo'shing (TELEGRAM_BOT_TOKEN qo'shganingizga o'xshab).
"""
import time
import sqlite3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config
from database import get_conn

router = APIRouter()


def _init_activation_table():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                tier TEXT NOT NULL,
                method TEXT NOT NULL,  -- 'code' | 'auto'
                created_at INTEGER NOT NULL
            )
        """)
        conn.commit()


_init_activation_table()


class LogActivation(BaseModel):
    tier: str  # 'main' | 'ai' | 'bundle'
    phone: str = ""
    method: str = "code"


@router.post("/api/admin/log-activation")
def log_activation(req: LogActivation):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO activation_log (phone, tier, method, created_at) VALUES (?, ?, ?, ?)",
            (req.phone or None, req.tier, req.method, int(time.time())),
        )
        conn.commit()
    return {"success": True}


@router.get("/api/admin/stats")
def admin_stats(key: str = ""):
    if not config.ADMIN_KEY or key != config.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    with get_conn() as conn:
        # Qo'lda kod orqali faollashtirishlar (tarif bo'yicha)
        code_rows = conn.execute(
            "SELECT tier, COUNT(*) as c FROM activation_log WHERE method='code' GROUP BY tier"
        ).fetchall()
        # Referral orqali ro'yxatdan o'tgan (kod olgan) noyob telefon raqamlar soni
        referral_users = conn.execute("SELECT COUNT(*) as c FROM referral_codes").fetchone()
        # Muvaffaqiyatli taklif qilingan (do'st qo'shilgan) soni
        referral_success = conn.execute("SELECT COUNT(*) as c FROM referral_redemptions").fetchone()
        # Avtomatik to'lov orqali HOZIR faol obunalar (tarif bo'yicha)
        now = int(time.time())
        auto_active = conn.execute(
            "SELECT tier, COUNT(*) as c FROM subscriptions WHERE expires_at > ? GROUP BY tier", (now,)
        ).fetchall()
        # Umumiy to'langan buyurtmalar (avtomatik tizim orqali, tarixiy)
        auto_paid_total = conn.execute(
            "SELECT COUNT(*) as c FROM orders WHERE status='paid'"
        ).fetchone()

    return {
        "qolda_kod_orqali": {row["tier"]: row["c"] for row in code_rows},
        "avtomatik_hozir_faol": {row["tier"]: row["c"] for row in auto_active},
        "avtomatik_jami_tolangan": auto_paid_total["c"],
        "referral_royxatdan_otgan": referral_users["c"],
        "referral_muvaffaqiyatli_taklif": referral_success["c"],
    }
