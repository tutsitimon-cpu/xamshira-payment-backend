import sqlite3
import time
import uuid
from contextlib import contextmanager

from config import DATABASE_PATH, SUBSCRIPTION_DAYS

# To'rtta tarif, guruhga (hamshira='orta' / shifokor='vrach') qarab narxi farqlanadi.
# 'ai' va 'bundle' — guruhdan qat'i nazar bir xil (bundle guruh bo'yicha alohida bo'lsa ham,
# ATMOS orqali qaysi guruh ekanini 'group' parametri orqali bilib olamiz).
TIER_PRICES_SOM = {
    "toifa": {"orta": 25000, "vrach": 50000},
    "specialty": {"orta": 50000, "vrach": 100000},
    "ai": {"orta": 20000, "vrach": 20000},
    "bundle": {"orta": 110000, "vrach": 220000},
}


def get_tier_price(tier: str, group: str = "orta") -> int:
    prices = TIER_PRICES_SOM.get(tier, TIER_PRICES_SOM["toifa"])
    return prices.get(group, prices.get("orta", 0))


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,          -- merchant_trans_id (bizning buyurtma raqamimiz)
                phone TEXT NOT NULL,          -- foydalanuvchi telefon raqami (obunani shu bilan bog'laymiz)
                amount_tiyin INTEGER NOT NULL,
                tier TEXT NOT NULL DEFAULT 'toifa',  -- 'toifa' | 'specialty' | 'ai' | 'bundle'
                group_name TEXT NOT NULL DEFAULT 'orta',  -- 'orta' (hamshira) | 'vrach' (shifokor)
                specialty_key TEXT,           -- masalan 'hamshiralik-ishi' (toifa/specialty tarifi uchun)
                toifa_key TEXT,                -- masalan '1-toifa' (faqat 'toifa' tarifi uchun)
                provider TEXT,                -- 'click' | 'payme' | 'paynet' | 'atmos'
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
                tier TEXT NOT NULL DEFAULT 'toifa',
                specialty_key TEXT,
                toifa_key TEXT
            )
        """)
        # Eski bazalarda ustunlar bo'lmasligi mumkin — bo'lsa ham xato bermasin
        for stmt in [
            "ALTER TABLE orders ADD COLUMN tier TEXT NOT NULL DEFAULT 'toifa'",
            "ALTER TABLE orders ADD COLUMN group_name TEXT NOT NULL DEFAULT 'orta'",
            "ALTER TABLE orders ADD COLUMN specialty_key TEXT",
            "ALTER TABLE orders ADD COLUMN toifa_key TEXT",
            "ALTER TABLE subscriptions ADD COLUMN tier TEXT NOT NULL DEFAULT 'toifa'",
            "ALTER TABLE subscriptions ADD COLUMN specialty_key TEXT",
            "ALTER TABLE subscriptions ADD COLUMN toifa_key TEXT",
        ]:
            try:
                conn.execute(stmt)
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


def create_order(phone: str, amount_tiyin: int, provider: str, tier: str = "toifa",
                  group_name: str = "orta", specialty_key: str = None, toifa_key: str = None) -> str:
    order_id = uuid.uuid4().hex[:16]
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO orders (id, phone, amount_tiyin, tier, group_name, specialty_key, toifa_key, "
            "provider, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (order_id, phone, amount_tiyin, tier, group_name, specialty_key, toifa_key,
             provider, int(time.time())),
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
        extend_subscription(
            order["phone"], tier=order["tier"],
            specialty_key=order["specialty_key"], toifa_key=order["toifa_key"],
        )


def mark_order_canceled(order_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status='canceled' WHERE id=?", (order_id,))
        conn.commit()


def extend_subscription(phone: str, tier: str = "toifa", days: int = None,
                         specialty_key: str = None, toifa_key: str = None):
    """Har bir muvaffaqiyatli to'lov — alohida "qatlam" sifatida qo'shiladi
    (masalan avval bitta toifa, keyin boshqa yo'nalish sotib olinsa, ikkalasi
    ham amal qiladi). Oddiy 1-qatorli 'subscriptions' jadvali o'rniga, buni
    to'g'ri saqlash uchun alohida 'active_unlocks' jadvali ishlatiladi."""
    days = days or SUBSCRIPTION_DAYS
    now = int(time.time())
    expires_at = now + days * 86400
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS active_unlocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                tier TEXT NOT NULL,
                specialty_key TEXT,
                toifa_key TEXT,
                expires_at INTEGER NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO active_unlocks (phone, tier, specialty_key, toifa_key, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (phone, tier, specialty_key, toifa_key, expires_at),
        )
        conn.commit()


def get_subscription_status(phone: str):
    """Shu telefon raqami uchun HOZIR faol bo'lgan barcha ochilishlarni
    qaytaradi — ilova shu ro'yxatga qarab, qaysi mutaxassislik/toifa ochiq
    ekanini o'zi hisoblab oladi."""
    now = int(time.time())
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS active_unlocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                tier TEXT NOT NULL,
                specialty_key TEXT,
                toifa_key TEXT,
                expires_at INTEGER NOT NULL
            )
        """)
        rows = conn.execute(
            "SELECT tier, specialty_key, toifa_key, expires_at FROM active_unlocks "
            "WHERE phone=? AND expires_at > ?", (phone, now)
        ).fetchall()

    is_ai_premium = False
    all_unlocked = False
    unlocked_specialties = []  # butun yo'nalish (barcha toifa) ochilgan
    unlocked_toifas = []       # "specialty_key:toifa_key" formatida

    for row in rows:
        if row["tier"] == "ai":
            is_ai_premium = True
        elif row["tier"] == "bundle":
            all_unlocked = True
            is_ai_premium = True
        elif row["tier"] == "specialty" and row["specialty_key"]:
            unlocked_specialties.append(row["specialty_key"])
        elif row["tier"] == "toifa" and row["specialty_key"] and row["toifa_key"]:
            unlocked_toifas.append(f"{row['specialty_key']}:{row['toifa_key']}")

    active = len(rows) > 0
    return {
        "active": active,
        "is_ai_premium": is_ai_premium,
        "all_unlocked": all_unlocked,
        "unlocked_specialties": unlocked_specialties,
        "unlocked_toifas": unlocked_toifas,
    }
