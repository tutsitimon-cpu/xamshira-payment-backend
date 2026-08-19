"""
Barcha maxfiy kalitlar (.env) fayldan o'qiladi. Hech qachon bu qiymatlarni
to'g'ridan-to'g'ri kodga yozmang yoki GitHub'ga push qilmang.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Obuna narxi va muddati ---
SUBSCRIPTION_PRICE_SOM = int(os.getenv("SUBSCRIPTION_PRICE_SOM", "35000"))
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))

# AI Yordamchi
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "claude-haiku-4-5-20251001")
AI_SUBSCRIPTION_PRICE_SOM = int(os.getenv("AI_SUBSCRIPTION_PRICE_SOM", "20000"))
AI_SUBSCRIPTION_DAYS = int(os.getenv("AI_SUBSCRIPTION_DAYS", "30"))

# AI Yordamchi — Gemini (bepul tarif, console.anthropic.com o'rniga
# aistudio.google.com'dan olinadigan kalit bilan ishlaydi)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")  # "gemini" yoki "anthropic"

# --- CLICK ---
CLICK_SERVICE_ID = os.getenv("CLICK_SERVICE_ID", "")
CLICK_MERCHANT_ID = os.getenv("CLICK_MERCHANT_ID", "")
CLICK_MERCHANT_USER_ID = os.getenv("CLICK_MERCHANT_USER_ID", "")
CLICK_SECRET_KEY = os.getenv("CLICK_SECRET_KEY", "")

# --- PAYME ---
PAYME_MERCHANT_ID = os.getenv("PAYME_MERCHANT_ID", "")
PAYME_SECRET_KEY = os.getenv("PAYME_SECRET_KEY", "")  # Test key yoki Production key
PAYME_TEST_MODE = os.getenv("PAYME_TEST_MODE", "true").lower() == "true"

# --- PAYNET ---
PAYNET_MERCHANT_ID = os.getenv("PAYNET_MERCHANT_ID", "")
# Eslatma: Paynet.uz ning webhook (IPN) imzo tekshirish sxemasi merchant
# panelidan olingandan so'ng shu yerga qo'shiladi — hozircha to'lov havolasini
# yaratish (redirect) qismi tayyor, webhook qismi TODO sifatida qoldirilgan.

# --- ATMOS (unified aggregator: Click/Payme/Uzcard/Humo/Visa/Mastercard) ---
# Kalitlar ATMOS bilan shartnoma imzolangach, ular tomonidan beriladi.
ATMOS_CONSUMER_KEY = os.getenv("ATMOS_CONSUMER_KEY", "")
ATMOS_CONSUMER_SECRET = os.getenv("ATMOS_CONSUMER_SECRET", "")
ATMOS_STORE_ID = os.getenv("ATMOS_STORE_ID", "")
ATMOS_TEST_MODE = os.getenv("ATMOS_TEST_MODE", "true").lower() == "true"  # production kalitlar kelgach "false" qilinadi
# Fixie orqali statik IP — ATMOS whitelist qilgan IP'lardan so'rov yuborish uchun
FIXIE_URL = os.getenv("FIXIE_URL", "")  # masalan: http://fixie:PASS@ventoux.usefixie.com:80

# --- Umumiy ---
DATABASE_PATH = os.getenv("DATABASE_PATH", "subscriptions.db")

# --- Qo'llab-quvvatlash xabarlarini Telegram'ga yuborish ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")  # @BotFather'dan olingan token — faqat Render env var sifatida kiritiladi
DEVELOPER_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID", "684813775")  # Xabarlar shu Telegram hisobga yuboriladi

# --- Statistika sahifasi ---
ADMIN_KEY = os.getenv("ADMIN_KEY", "")  # Statistikani ko'rish uchun maxfiy kalit — Render'da o'zingiz belgilaysiz
