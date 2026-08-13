# Xamshira Test — Android APK

Bu papka ilovangizni haqiqiy Android APK'ga aylantirish uchun tayyor.
APK'ni kompyuteringizda emas, **GitHub'ning o'zida, avtomatik** yig'amiz —
sizga Android Studio o'rnatish shart emas.

## 1-qadam: GitHub'ga yuklash

1. github.com'da **yangi repository** yarating (masalan nomi: `xamshira-test-apk`)
2. Shu papkadagi **barcha fayl va papkalarni** (`.github` papkasi ham kiradi —
   u yashirin bo'lgani uchun ko'rinmasligi mumkin, lekin muhim!) repo'ga yuklang

**Muhim eslatma:** GitHub veb-saytidan oddiy "upload files" orqali yuklaganda,
ba'zan `.github` papkasi (nuqta bilan boshlanadigan yashirin papkalar)
to'g'ri yuklanmasligi mumkin. Agar shunday bo'lsa, menga ayting — muqobil
yo'l (zip orqali) ko'rsataman.

## 2-qadam: Qurilishni kuzatish

1. GitHub'da repo sahifangizga o'ting
2. Yuqoridagi **"Actions"** bo'limini bosing
3. "Build Android APK" ishi avtomatik boshlangan bo'lishi kerak (yashil ✓
   yoki sariq ⏳ belgi bilan) — bu ~3-5 daqiqa davom etadi

## 3-qadam: Tayyor APK'ni yuklab olish

1. Ish tugagach (yashil ✓), o'sha ish sahifasini oching
2. Pastda **"Artifacts"** bo'limida `xamshira-test-debug-apk` deb nomlangan
   faylni bosib yuklab oling (bu — zip ichida .apk fayl)
3. Zipni oching, `.apk` faylni telefoningizga o'tkazib, o'rnating (birinchi
   marta "Noma'lum manbalardan o'rnatishga ruxsat berish" so'ralishi mumkin
   — bu normal, ilova hali Play Market orqali emas, to'g'ridan-to'g'ri
   o'rnatilyapti)

## Eslatma: bu "debug" versiya

Hozircha yig'ilayotgan APK — **sinov (debug) versiyasi**. U to'liq ishlaydi,
lekin Play Market'ga yuklash uchun **"release" versiya** kerak bo'ladi —
bu uchun ilovani raqamli imzo (signing key) bilan imzolash kerak. Bu
keyingi bosqich — hozircha sinov versiyasini tekshirib, hammasi to'g'ri
ishlayotganiga ishonch hosil qilaylik, keyin release versiyasiga o'tamiz.

## Keyingi qadamlar (keyinroq)

- Ilova ikonkasi va nomini moslashtirish
- Release (imzolangan) versiya yig'ish
- Google Play Developer hisobiga yuklash ($25 bir martalik)
