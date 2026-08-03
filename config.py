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

# --- Umumiy ---
DATABASE_PATH = os.getenv("DATABASE_PATH", "subscriptions.db")
