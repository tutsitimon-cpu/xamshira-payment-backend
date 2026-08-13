import sqlite3
import time
import uuid
from contextlib import contextmanager

from config import DATABASE_PATH, SUBSCRIPTION_DAYS

# Uchta tarif: 'main' (test+og'zaki), 'ai' (AI Yordamchi), 'bundle' (ikkalasi)
TIER_PRICES_SOM = {"main": 35000, "ai": 20000, "bundle": 55000}


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,          -- merchant_trans_id (bizning buyurtma raqamimiz)
                phone TEXT NOT NULL,          -- foydalanuvchi telefon raqami (obunani shu bilan bog'laymiz)
                amount_tiyin INTEGER NOT NULL,
                tier TEXT NOT NULL DEFAULT 'main',  -- 'main' | 'ai' | 'bundle'
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
                expires_at INTEGER NOT NULL,
                tier TEXT NOT NULL DEFAULT 'main'
            )
        """)
        # Eski bazalarda "tier" ustuni bo'lmasligi mumkin — bo'lsa ham xato bermasin
        try:
            conn.execute("ALTER TABLE orders ADD COLUMN tier TEXT NOT NULL DEFAULT 'main'")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE subscriptions ADD COLUMN tier TEXT NOT NULL DEFAULT 'main'")
        except sqlite3.OperationalError:
            pass
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def create_order(phone: str, amount_tiyin: int, provider: str, tier: str = "main") -> str:
    order_id = uuid.uuid4().hex[:16]
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO orders (id, phone, amount_tiyin, tier, provider, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (order_id, phone, amount_tiyin, tier, provider, int(time.time())),
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
        extend_subscription(order["phone"], tier=order["tier"])


def mark_order_canceled(order_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status='canceled' WHERE id=?", (order_id,))
        conn.commit()


def extend_subscription(phone: str, tier: str = "main", days: int = None):
    """Yangi tarif eskisidan "kuchliroq" bo'lsa, ustiga yozadi (masalan avval
    faqat 'main' bo'lgan, endi 'bundle' sotib olsa, 'bundle'ga ko'tariladi).
    Bir xil tarif ichida esa muddat cho'ziladi (davomiylik yo'qolmaydi)."""
    days = days or SUBSCRIPTION_DAYS
    now = int(time.time())
    add_seconds = days * 86400
    tier_rank = {"main": 1, "ai": 1, "bundle": 2}
    with get_conn() as conn:
        row = conn.execute("SELECT expires_at, tier FROM subscriptions WHERE phone=?", (phone,)).fetchone()
        if row and row["expires_at"] > now:
            new_expiry = row["expires_at"] + add_seconds
            # Eski va yangi tarifning eng "kuchlisi"ni tanlaymiz (bundle > main/ai)
            if tier_rank.get(tier, 1) >= tier_rank.get(row["tier"], 1):
                new_tier = tier
            else:
                new_tier = row["tier"]
        else:
            new_expiry = now + add_seconds
            new_tier = tier
        conn.execute(
            "INSERT INTO subscriptions (phone, expires_at, tier) VALUES (?, ?, ?) "
            "ON CONFLICT(phone) DO UPDATE SET expires_at=excluded.expires_at, tier=excluded.tier",
            (phone, new_expiry, new_tier),
        )
        conn.commit()


def get_subscription_status(phone: str):
    with get_conn() as conn:
        row = conn.execute("SELECT expires_at, tier FROM subscriptions WHERE phone=?", (phone,)).fetchone()
    if not row:
        return {"active": False, "expires_at": None, "is_premium": False, "is_ai_premium": False}
    now = int(time.time())
    active = row["expires_at"] > now
    tier = row["tier"] if active else None
    return {
        "active": active,
        "expires_at": row["expires_at"],
        "is_premium": active and tier in ("main", "bundle"),
        "is_ai_premium": active and tier in ("ai", "bundle"),
    }
