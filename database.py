import sqlite3
import time
import uuid
from contextlib import contextmanager

from config import DATABASE_PATH, SUBSCRIPTION_DAYS


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,          -- merchant_trans_id (bizning buyurtma raqamimiz)
                phone TEXT NOT NULL,          -- foydalanuvchi telefon raqami (obunani shu bilan bog'laymiz)
                amount_tiyin INTEGER NOT NULL,
                provider TEXT,                -- 'click' | 'payme' | 'paynet'
                status TEXT NOT NULL DEFAULT 'pending',  -- pending | paid | canceled
                external_id TEXT,             -- provider tomonidan berilgan tranzaksiya id
                created_at INTEGER NOT NULL,
                paid_at INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                phone TEXT PRIMARY KEY,
                expires_at INTEGER NOT NULL
            )
        """)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def create_order(phone: str, amount_tiyin: int, provider: str) -> str:
    order_id = uuid.uuid4().hex[:16]
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO orders (id, phone, amount_tiyin, provider, status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (order_id, phone, amount_tiyin, provider, int(time.time())),
        )
        conn.commit()
    return order_id


def get_order(order_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return dict(row) if row else None


def mark_order_paid(order_id: str, external_id: str = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status='paid', external_id=?, paid_at=? WHERE id=?",
            (external_id, int(time.time()), order_id),
        )
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        conn.commit()
    if order:
        extend_subscription(order["phone"])


def mark_order_canceled(order_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status='canceled' WHERE id=?", (order_id,))
        conn.commit()


def extend_subscription(phone: str, days: int = None):
    days = days or SUBSCRIPTION_DAYS
    now = int(time.time())
    add_seconds = days * 86400
    with get_conn() as conn:
        row = conn.execute("SELECT expires_at FROM subscriptions WHERE phone=?", (phone,)).fetchone()
        if row and row["expires_at"] > now:
            # Muddati tugamagan bo'lsa, ustiga qo'shamiz (davomiylik yo'qolmaydi)
            new_expiry = row["expires_at"] + add_seconds
        else:
            new_expiry = now + add_seconds
        conn.execute(
            "INSERT INTO subscriptions (phone, expires_at) VALUES (?, ?) "
            "ON CONFLICT(phone) DO UPDATE SET expires_at=excluded.expires_at",
            (phone, new_expiry),
        )
        conn.commit()


def get_subscription_status(phone: str):
    with get_conn() as conn:
        row = conn.execute("SELECT expires_at FROM subscriptions WHERE phone=?", (phone,)).fetchone()
    if not row:
        return {"active": False, "expires_at": None}
    now = int(time.time())
    return {"active": row["expires_at"] > now, "expires_at": row["expires_at"]}
