"""Bilingual (Bahasa Melayu / English) UI strings.

Keep both languages in sync. Use t(lang, "key") in Python; `t` is also a
Jinja global so templates call {{ t("key") }} with the request's language.
"""
from __future__ import annotations

LANGS = ("ms", "en")

STRINGS: dict[str, dict[str, str]] = {
    # generic
    "brand": {"ms": "Johor Studio", "en": "Johor Studio"},
    "nav_orders": {"ms": "Order Saya", "en": "My Orders"},
    "nav_login": {"ms": "Log Masuk", "en": "Log In"},
    "nav_logout": {"ms": "Log Keluar", "en": "Log Out"},
    "lang_switch": {"ms": "EN", "en": "BM"},
    "back": {"ms": "Kembali", "en": "Back"},
    "continue": {"ms": "Teruskan", "en": "Continue"},
    "cancel": {"ms": "Batal", "en": "Cancel"},
    "search": {"ms": "Cari no. gambar / nama fail", "en": "Search photo no. / filename"},
    "all_schools": {"ms": "Semua sekolah", "en": "All schools"},
    "all_classes": {"ms": "Semua kelas", "en": "All classes"},
    # gallery / cart
    "choose_photos": {"ms": "Pilih gambar", "en": "Choose photos"},
    "add_to_cart": {"ms": "Tambah ke troli", "en": "Add to cart"},
    "in_cart": {"ms": "Dalam troli", "en": "In cart"},
    "cart": {"ms": "Troli", "en": "Cart"},
    "view_cart": {"ms": "Lihat troli", "en": "View cart"},
    "cart_empty": {"ms": "Troli kosong", "en": "Your cart is empty"},
    "size": {"ms": "Saiz", "en": "Size"},
    "qty": {"ms": "Kuantiti", "en": "Qty"},
    "remove": {"ms": "Buang", "en": "Remove"},
    "add_more": {"ms": "Tambah gambar lain", "en": "Add more photos"},
    "subtotal": {"ms": "Jumlah kecil", "en": "Subtotal"},
    "total": {"ms": "Jumlah", "en": "Total"},
    "checkout": {"ms": "Teruskan ke pembayaran", "en": "Proceed to payment"},
    "added_toast": {"ms": "gambar ditambah ke troli", "en": "photos added to cart"},
    # delivery
    "delivery": {"ms": "Cara penghantaran", "en": "Delivery method"},
    "pickup": {"ms": "Ambil di sekolah", "en": "Pickup at school"},
    "post": {"ms": "Pos ke rumah", "en": "Post to home"},
    "postage": {"ms": "Caj pos", "en": "Postage"},
    "address": {"ms": "Alamat penuh", "en": "Full address"},
    "pin_location": {"ms": "Pin lokasi anda di peta", "en": "Pin your location on the map"},
    # auth
    "login_title": {"ms": "Log masuk untuk bayar", "en": "Log in to pay"},
    "email": {"ms": "E-mel", "en": "Email"},
    "send_code": {"ms": "Hantar kod", "en": "Send code"},
    "enter_code": {"ms": "Masukkan kod dari e-mel", "en": "Enter the code from your email"},
    "code_hint": {"ms": "Dua nombor, contoh: 21 88", "en": "Two numbers, e.g. 21 88"},
    "resend": {"ms": "Hantar semula", "en": "Resend"},
    "verify": {"ms": "Sahkan", "en": "Verify"},
    "your_phone": {"ms": "Nombor telefon anda", "en": "Your phone number"},
    "name_short": {"ms": "Nama (ringkas)", "en": "Name (short)"},
    "err_wrong_code": {"ms": "Kod salah. Cuba lagi.", "en": "Wrong code. Try again."},
    "err_locked": {"ms": "Terlalu banyak cubaan. Cuba sebentar lagi.", "en": "Too many attempts. Try again later."},
    "err_expired": {"ms": "Kod tamat tempoh. Minta kod baru.", "en": "Code expired. Request a new one."},
    "err_too_soon": {"ms": "Sila tunggu sebelum hantar semula.", "en": "Please wait before resending."},
    # payment
    "pay_title": {"ms": "Pembayaran", "en": "Payment"},
    "pay_how": {"ms": "Cara bayar", "en": "How to pay"},
    "pay_qrpay": {"ms": "Imbas QRPay", "en": "Scan QRPay"},
    "pay_transfer": {"ms": "Pindahan bank", "en": "Bank transfer"},
    "amount_to_pay": {"ms": "Jumlah untuk dibayar", "en": "Amount to pay"},
    "upload_receipt": {"ms": "Muat naik resit", "en": "Upload receipt"},
    "receipt_hint": {"ms": "PNG, JPG atau PDF · maksimum 10MB setiap satu", "en": "PNG, JPG or PDF · max 10MB each"},
    "balance_due": {"ms": "Baki perlu dibayar", "en": "Balance due"},
    "paid_so_far": {"ms": "Dibayar setakat ini", "en": "Paid so far"},
    "overpaid_note": {
        "ms": "Anda terlebih bayar. Kami akan hubungi anda melalui WhatsApp.",
        "en": "You have overpaid. We will contact you via WhatsApp.",
    },
    "dup_warning": {
        "ms": "Nombor resit ini sudah ada dalam rekod. Sila semak. Anda masih boleh hantar.",
        "en": "This receipt number is already on record. Please check. You may still submit.",
    },
    "force_submit": {"ms": "Hantar juga", "en": "Submit anyway"},
    # statuses
    "st_awaiting_payment": {"ms": "Menunggu bayaran", "en": "Awaiting payment"},
    "st_reviewing": {"ms": "Semakan resit", "en": "Reviewing receipt"},
    "st_paid": {"ms": "Lunas", "en": "Paid"},
    "st_printing": {"ms": "Sedang dicetak", "en": "Printing"},
    "st_ready": {"ms": "Siap / Dihantar", "en": "Ready / Shipped"},
    "st_cancelled": {"ms": "Dibatalkan", "en": "Cancelled"},
    # order page
    "my_order": {"ms": "Order Saya", "en": "My Order"},
    "order_no": {"ms": "No. order", "en": "Order no."},
    "status": {"ms": "Status", "en": "Status"},
    "open_in_maps": {"ms": "Buka dalam Google Maps", "en": "Open in Google Maps"},
    "contact_whatsapp": {"ms": "Hubungi kami di WhatsApp", "en": "Contact us on WhatsApp"},
    # footer
    "footer_website": {"ms": "Laman web", "en": "Website"},
    "terms": {"ms": "Terma", "en": "Terms"},
    "studio_addr": {
        "ms": "3038-A, Jln Merbau Satu, Bandar Putra, 81000 Kulai, Johor",
        "en": "3038-A, Jln Merbau Satu, Bandar Putra, 81000 Kulai, Johor",
    },
    "no_save_note": {
        "ms": "Gambar ini hak milik Johor Studio dan tidak boleh disimpan.",
        "en": "These photos belong to Johor Studio and may not be saved.",
    },
    "event_closed": {"ms": "Tempahan untuk majlis ini telah ditutup.", "en": "Ordering for this event is closed."},
}

STATUS_KEYS = {
    "awaiting_payment": "st_awaiting_payment",
    "reviewing": "st_reviewing",
    "paid": "st_paid",
    "printing": "st_printing",
    "ready": "st_ready",
    "cancelled": "st_cancelled",
}


def t(lang: str, key: str) -> str:
    lang = lang if lang in LANGS else "ms"
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get("ms", key))


def status_label(lang: str, status: str) -> str:
    return t(lang, STATUS_KEYS.get(status, status))
