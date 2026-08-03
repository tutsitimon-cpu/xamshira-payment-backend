# Xamshira Test — Obuna backend

Bu server 3 ta to'lov tizimini (Click, Payme, Paynet) ulash uchun kerak.
Ilova (veb yoki APK) to'g'ridan-to'g'ri Click/Payme bilan "gaplasha olmaydi" —
chunki maxfiy kalitlarni (SECRET_KEY) telefon ilovasi ichida saqlash xavfli
(istalgan kishi APK'ni ochib kalitni o'g'irlashi mumkin). Shuning uchun bu
kalitlar shu backend serverda, alohida joyda saqlanadi.

## 1. Nima uchun server kerak?

- Click/Payme/Paynet foydalanuvchi to'lov qilganda **sizning serveringizga**
  "to'lov bo'ldi" degan xabar (webhook) yuboradi.
- Bu xabar internetdan kirish mumkin bo'lgan **doimiy ishlaydigan, HTTPS
  manzilga ega** serverga kelishi kerak — shuning uchun oddiy kompyuteringizda
  ishga tushirib bo'lmaydi, xosting kerak.

## 2. Xosting tanlash

Sizda hozircha server yo'qligini hisobga olib, bir nechta variant:

| Variant | Narxi | Qulayligi |
|---|---|---|
| **Render.com** yoki **Railway.app** | Kichik loyihalar uchun bepul/arzon tarif bor | Eng oson — GitHub'ga kodni yuklaysiz, ular avtomatik ishga tushiradi, HTTPS o'zi beriladi |
| **Timeweb Cloud** yoki **Beget** (Rossiya, so'mda/rublda to'lov qulay) | ~$3-5/oy VPS | Ozroq texnik bilim kerak (SSH orqali ulanish), lekin to'liq nazorat sizda |
| **Hetzner / DigitalOcean** (xalqaro VPS) | ~$4-6/oy | Xalqaro karta kerak bo'lishi mumkin |

**Tavsiya:** Boshlash uchun eng tez yo'l — **Render.com**. GitHub'ga bu papkani
yuklab, Render'da "New Web Service" qilib bog'lasangiz, 10 daqiqada tayyor
bo'ladi, HTTPS manzil avtomatik beriladi (masalan
`https://xamshira-test.onrender.com`). Keyinchalik trafik oshsa, VPS'ga
ko'chirish mumkin.

## 3. Kerakli hujjatlar/kalitlar qayerdan olinadi

- **CLICK**: https://merchant.click.uz — ro'yxatdan o'tib, "Shop API" xizmatini
  yoqtirasiz. `SERVICE_ID`, `MERCHANT_ID`, `SECRET_KEY` shu yerdan olinadi.
- **PAYME**: https://business.payme.uz — "Kassa" yarating, `MERCHANT_ID` va
  `SECRET_KEY` (test va production alohida) shu yerdan olinadi.
- **PAYNET**: Paynet bilan bog'lanib merchant hisob oching — ular sizga
  `MERCHANT_ID` va webhook imzo tekshirish bo'yicha hujjat berishadi
  (`providers/paynet.py` faylidagi TODO qismini o'sha hujjatga qarab
  to'ldirasiz).

Har bir tizimning "Callback/Webhook URL" maydoniga serveringiz manzilini
yozib qo'yasiz, masalan:
- Click: `https://xamshira-test.onrender.com/payment/click`
- Payme: `https://xamshira-test.onrender.com/payment/payme`
- Paynet: `https://xamshira-test.onrender.com/payment/paynet`

## 4. Ishga tushirish (lokal sinov, ixtiyoriy)

```bash
pip install -r requirements.txt
cp .env.example .env      # keyin .env ichiga haqiqiy kalitlarni yozing
uvicorn main:app --reload --port 8000
```

Brauzerda `http://localhost:8000/docs` ga kirsangiz, barcha endpointlarni
sinab ko'rish mumkin (Swagger interfeysi).

## 5. Ilova bilan bog'lash

Ilova (xamshira_test_demo.html yoki kelajakdagi APK) quyidagi ikkita
endpointdan foydalanadi:

1. `POST /api/subscribe/init` — `{"phone": "998901234567"}` yuborsangiz,
   javobida 3 ta to'lov havolasi (Click/Payme/Paynet) qaytadi. Foydalanuvchi
   birini tanlab bosadi.
2. `GET /api/subscription/status?phone=998901234567` — ilova ochilganda
   shu orqali obuna faolmi-yo'qmi tekshiriladi.

Hozircha demo HTML faylida bu ikki endpoint hali ulanmagan (chunki
serveringiz manzili yo'q edi) — server tayyor bo'lgach, manzilni ayting,
men ilovani shu serverga ulab, to'lov tugmalarini haqiqiy qilib beraman.

## 6. Xavfsizlik eslatmalari

- `.env` faylini hech qachon ochiq joyga (GitHub public repo va h.k.)
  yubormang — ichida SECRET_KEY bor.
- Productionda `main.py` dagi `allow_origins=["*"]` qatorini o'z domeningiz
  bilan cheklang.
- `subscriptions.db` fayli — foydalanuvchilar va to'lovlar shu yerda
  saqlanadi. Muntazam zaxira (backup) oling.
