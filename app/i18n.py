"""Bilingual (Bahasa Melayu / English) UI strings.

Keep both languages in sync. Use t(lang, "key") in Python; `t` is also a
Jinja global so templates call {{ t("key") }} with the request's language.
"""
from __future__ import annotations

LANGS = ("ms", "en")

STRINGS: dict[str, dict[str, str]] = {
    # generic
    "brand": {"ms": "JohorStudio.com", "en": "JohorStudio.com"},
    "nav_orders": {"ms": "Order Saya", "en": "My Orders"},
    "nav_login": {"ms": "Log Masuk", "en": "Log In"},
    "nav_logout": {"ms": "Log Keluar", "en": "Log Out"},
    "lang_switch": {"ms": "EN", "en": "BM"},
    "language": {"ms": "Bahasa", "en": "Language"},
    "back": {"ms": "Kembali", "en": "Back"},
    "continue": {"ms": "Teruskan", "en": "Continue"},
    "cancel": {"ms": "Batal", "en": "Cancel"},
    "search": {"ms": "Cari no. gambar / nama fail", "en": "Search photo no. / filename"},
    "all_schools": {"ms": "Semua kategori", "en": "All categories"},
    "all_classes": {"ms": "Semua album", "en": "All albums"},
    "category": {"ms": "Kategori", "en": "Category"},
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
    "err_no_sizes": {"ms": "Saiz cetakan belum ditetapkan untuk majlis ini.", "en": "Print sizes are not set for this event yet."},
    "err_generic": {"ms": "Ralat. Cuba lagi.", "en": "Something went wrong. Try again."},
    "zoom": {"ms": "Besarkan", "en": "Zoom"},
    "close": {"ms": "Tutup", "en": "Close"},
    "already_in_cart": {"ms": "Gambar ini sudah ada dalam troli.", "en": "These photos are already in your cart."},
    "pick_size": {"ms": "Pilih saiz cetakan:", "en": "Choose a print size:"},
    "per_print": {"ms": "keping", "en": "print"},
    "add_other_size": {"ms": "Cetak saiz lain juga", "en": "Also print in another size"},
    "unsized_left": {"ms": "{n} gambar belum dipilih saiz. Pilih saiz untuk teruskan.",
                     "en": "{n} photo(s) still need a size. Choose a size to continue."},
    "need_size_err": {"ms": "Sila pilih saiz untuk semua gambar dahulu.", "en": "Please choose a size for every photo first."},
    "view_photo": {"ms": "Lihat gambar", "en": "View photo"},
    "pickup_choose": {"ms": "Pilih lokasi ambil", "en": "Choose a pickup point"},
    "pickup_required": {"ms": "Sila pilih lokasi ambil.", "en": "Please choose a pickup point."},
    "qr_save": {"ms": "Simpan gambar QR", "en": "Save QR image"},
    "qr_step1": {"ms": "Tekan QR atau butang \"Simpan gambar QR\" untuk simpan ke galeri telefon.",
                 "en": "Tap the QR or \"Save QR image\" to save it to your phone's gallery."},
    "qr_step2": {"ms": "Buka app bank atau e-wallet anda, pilih Scan, kemudian pilih gambar QR dari galeri.",
                 "en": "Open your bank or e-wallet app, choose Scan, then pick the QR image from your gallery."},
    "qr_step3": {"ms": "Masukkan jumlah tepat {amt} dan bayar. Simpan resit.",
                 "en": "Key in the exact amount {amt} and pay. Keep the receipt."},
    "qr_step3_dn": {"ms": "Jumlah {amt} sudah termasuk dalam QR. Sahkan dan bayar, kemudian simpan resit.",
                    "en": "The amount {amt} is already in the QR. Confirm and pay, then keep the receipt."},
    "qr_other_phone": {"ms": "Buka halaman ini di komputer? Imbas QR terus dengan app bank di telefon anda.",
                       "en": "Viewing this on a computer? Scan the QR directly with your bank app."},
    "receipt_submit_note": {"ms": "Order hanya dihantar untuk diproses selepas resit pembayaran dimuat naik.",
                            "en": "Your order is only sent for processing after the payment receipt is uploaded."},
    "editable_tag": {"ms": "Boleh diubah", "en": "Editable"},
    "edit_hint": {"ms": "Anda boleh tukar saiz, kuantiti atau buang gambar sebelum upload resit. Jumlah dan QR dikemas kini terus.",
                  "en": "You can change sizes, quantities or remove photos before uploading a receipt. The total and QR update instantly."},
    "order_locked": {"ms": "Order ini tidak boleh diubah lagi kerana resit sudah dihantar.",
                     "en": "This order can no longer be changed because a receipt has been sent."},
    "order_last_item": {"ms": "Order perlu ada sekurang-kurangnya satu gambar. Untuk batal, hubungi kami di WhatsApp.",
                        "en": "An order needs at least one photo. To cancel, contact us on WhatsApp."},
    # delivery
    "delivery": {"ms": "Cara penghantaran", "en": "Delivery method"},
    "pickup": {"ms": "Ambil sendiri", "en": "Self pickup"},
    "post_only_note": {"ms": "Cetakan akan dipos ke alamat anda.", "en": "Your prints will be posted to your address."},
    "post": {"ms": "Pos ke rumah", "en": "Post to home"},
    "postage": {"ms": "Caj pos", "en": "Postage"},
    "address": {"ms": "Alamat penuh", "en": "Full address"},
    "pin_location": {"ms": "Pin lokasi anda di peta", "en": "Pin your location on the map"},
    # auth
    "login_title": {"ms": "Log masuk untuk bayar", "en": "Log in to pay"},
    "email": {"ms": "E-mel", "en": "Email"},
    "send_code": {"ms": "Hantar kod", "en": "Send code"},
    "enter_code": {"ms": "Masukkan kod dari e-mel", "en": "Enter the code from your email"},
    "code_hint": {"ms": "Kod 4 nombor, contoh: 2188", "en": "4-digit code, e.g. 2188"},
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
    "help_whatsapp": {"ms": "Soalan dan bantuan", "en": "Questions & help"},
    "help_note": {"ms": "Ada soalan tentang order atau bayaran? Kami sedia membantu di WhatsApp.",
                  "en": "Questions about your order or payment? We're happy to help on WhatsApp."},
    "help_msg": {"ms": "Hi Rafi, saya ada soalan tentang tempahan gambar", "en": "Hi Rafi, I have a question about my photo order"},
    # home
    "home_title": {"ms": "Galeri Majlis", "en": "Event Galleries"},
    "home_lead": {"ms": "Pilih majlis anda untuk melihat dan menempah cetakan gambar.",
                  "en": "Choose your event to view and order photo prints."},
    "open_gallery": {"ms": "Buka galeri", "en": "Open gallery"},
    "no_events": {"ms": "Tiada galeri dibuka buat masa ini. Jika anda ada link galeri, buka link tersebut.",
                  "en": "No galleries are open right now. If you have a gallery link, please open it."},
    "how1_t": {"ms": "Pilih gambar", "en": "Choose photos"},
    "how1_d": {"ms": "Buka galeri majlis anda dan tanda gambar yang dikehendaki.", "en": "Open your event gallery and tick the photos you want."},
    "how2_t": {"ms": "Pilih saiz & bayar", "en": "Pick sizes & pay"},
    "how2_d": {"ms": "Tetapkan saiz cetakan, bayar melalui QR atau pindahan bank, kemudian upload resit.", "en": "Set print sizes, pay by QR or bank transfer, then upload your receipt."},
    "how3_t": {"ms": "Terima cetakan", "en": "Receive your prints"},
    "how3_d": {"ms": "Kami cetak dan sediakan untuk diambil atau dipos.", "en": "We print them, ready for pickup or posting."},
    "help_full": {"ms": "Panduan penuh", "en": "Full guide"},
    "our_work": {"ms": "Hasil kerja kami", "en": "Our work"},
    "see_portfolio": {"ms": "Lihat portfolio di JohorStudio.com", "en": "See our portfolio on JohorStudio.com"},
    "prev": {"ms": "Sebelum", "en": "Previous"},
    "next": {"ms": "Seterusnya", "en": "Next"},
    "nav_shop": {"ms": "Shop", "en": "Shop"},
    "nav_help": {"ms": "Bantuan", "en": "Help"},
    # help page
    "help_title": {"ms": "Cara Membeli", "en": "How to Order"},
    "help_lead": {"ms": "Tempahan cetakan gambar dalam enam langkah mudah. Semua gambar dicetak oleh JohorStudio.com.",
                  "en": "Order photo prints in six simple steps. All photos are printed by JohorStudio.com."},
    "hs1_t": {"ms": "Buka galeri majlis", "en": "Open your event gallery"},
    "hs1_d": {"ms": "Pilih majlis di halaman utama, atau buka link galeri yang diberikan kepada anda.",
              "en": "Choose your event on the main page, or open the gallery link you were given."},
    "hs2_t": {"ms": "Tanda gambar", "en": "Tick your photos"},
    "hs2_d": {"ms": "Sentuh gambar untuk memilih. Guna ikon besarkan untuk melihat dengan jelas, dan penapis untuk mencari album atau nombor gambar. Tekan \"Tambah ke troli\".",
              "en": "Tap a photo to select it. Use the zoom icon to view it larger, and the filters to find an album or photo number. Then tap \"Add to cart\"."},
    "hs3_t": {"ms": "Pilih saiz dan kuantiti", "en": "Choose size and quantity"},
    "hs3_d": {"ms": "Di troli, tetapkan saiz cetakan dan bilangan salinan bagi setiap gambar. Harga dikira terus.",
              "en": "In the cart, set the print size and number of copies for each photo. The total updates instantly."},
    "hs4_t": {"ms": "Log masuk dengan e-mel", "en": "Log in with your email"},
    "hs4_d": {"ms": "Masukkan e-mel anda. Kami hantar kod 4 nombor, masukkan kod itu, kemudian isi nombor telefon untuk dihubungi.",
              "en": "Enter your email. We send a 4-digit code; enter it, then add a phone number we can reach you on."},
    "hs5_t": {"ms": "Bayar dan upload resit", "en": "Pay and upload your receipt"},
    "hs5_d": {"ms": "Bayar jumlah tepat melalui QR atau pindahan bank, kemudian upload resit (PNG, JPG atau PDF). Resit disemak secara automatik.",
              "en": "Pay the exact amount by QR or bank transfer, then upload the receipt (PNG, JPG or PDF). Receipts are checked automatically."},
    "hs6_t": {"ms": "Ambil atau terima cetakan", "en": "Collect or receive your prints"},
    "hs6_d": {"ms": "Ikuti status di \"Order Saya\". Cetakan disediakan untuk diambil di lokasi yang ditetapkan, atau dipos jika anda memilih pos.",
              "en": "Track the status under \"My Orders\". Prints are ready to collect at the stated location, or posted if you chose postage."},
    "faq_title": {"ms": "Soalan lazim", "en": "Common questions"},
    "faq1_q": {"ms": "Boleh saya muat turun gambar digital?", "en": "Can I download the digital photos?"},
    "faq1_a": {"ms": "Tidak. Shop ini untuk tempahan cetakan sahaja. Gambar di galeri adalah pratonton dan hak milik JohorStudio.com.",
               "en": "No. This shop is for print orders only. Gallery images are previews and belong to JohorStudio.com."},
    "faq2_q": {"ms": "Saya tak terima kod log masuk.", "en": "I didn't receive the login code."},
    "faq2_a": {"ms": "Semak folder spam atau promosi, dan pastikan e-mel ditulis betul. Anda boleh tekan \"Hantar semula\" selepas seketika.",
               "en": "Check your spam or promotions folder and make sure the email is correct. You can tap \"Resend\" after a moment."},
    "faq3_q": {"ms": "Saya terkurang atau terlebih bayar.", "en": "I paid too little or too much."},
    "faq3_a": {"ms": "Jika terkurang, halaman order akan tunjuk baki untuk dibayar. Jika terlebih, kami akan hubungi anda melalui WhatsApp.",
               "en": "If you underpaid, your order page shows the balance to pay. If you overpaid, we will contact you via WhatsApp."},
    "faq4_q": {"ms": "Resit saya belum disahkan.", "en": "My receipt hasn't been confirmed."},
    "faq4_a": {"ms": "Resit yang tidak dapat dibaca dengan jelas akan disemak secara manual oleh kami. Status akan dikemas kini di \"Order Saya\".",
               "en": "Receipts that can't be read clearly are checked manually by us. The status will update under \"My Orders\"."},
    "faq5_q": {"ms": "Boleh saya tambah gambar selepas bayar?", "en": "Can I add photos after paying?"},
    "faq5_a": {"ms": "Buat order baru untuk gambar tambahan selagi galeri masih dibuka.",
               "en": "Place a new order for extra photos while the gallery is still open."},
    # footer
    "footer_website": {"ms": "Laman web", "en": "Website"},
    "terms": {"ms": "Terma", "en": "Terms"},
    "foot_tagline": {
        "ms": "Penyedia media digital profesional sejak 2014. Fotografi, videografi, multicamera production dan livestreaming di seluruh Malaysia.",
        "en": "Professional digital media provider since 2014. Photography, videography, multicamera production and livestreaming across Malaysia.",
    },
    "foot_contact": {"ms": "Hubungi", "en": "Contact"},
    "foot_call": {"ms": "Telefon", "en": "Call"},
    "foot_appointment": {"ms": "Dengan temujanji sahaja", "en": "By appointment only"},
    "foot_links": {"ms": "Pautan", "en": "Links"},
    "studio_addr": {
        "ms": "3038-A, Jln Merbau Satu, Bandar Putra, 81000 Kulai, Johor",
        "en": "3038-A, Jln Merbau Satu, Bandar Putra, 81000 Kulai, Johor",
    },
    "no_save_note": {
        "ms": "Gambar ini hak milik JohorStudio.com dan tidak boleh disimpan.",
        "en": "These photos belong to JohorStudio.com and may not be saved.",
    },
    # receipt OCR feedback (per receipt, on the order page)
    "ocr_title": {"ms": "Semakan resit", "en": "Receipt check"},
    "ocr_detected": {"ms": "Amaun dikesan", "en": "Amount detected"},
    "ocr_note_match": {"ms": "Sepadan dengan jumlah order. Bayaran disahkan.",
                       "en": "Matches the order total. Payment confirmed."},
    "ocr_note_partial": {"ms": "Kurang daripada jumlah order. Sila bayar baki dan upload resit baki.",
                         "en": "Less than the order total. Please pay the balance and upload that receipt."},
    "ocr_note_over": {"ms": "Lebih daripada jumlah order. Kami akan hubungi anda melalui WhatsApp.",
                      "en": "More than the order total. We will contact you via WhatsApp."},
    "ocr_note_unreadable": {"ms": "Resit tidak dapat dibaca secara automatik. Kami akan semak secara manual.",
                            "en": "The receipt couldn't be read automatically. We will check it manually."},
    "ocr_note_no_amount": {"ms": "Amaun tidak dijumpai pada resit. Kami akan semak secara manual.",
                           "en": "No amount was found on the receipt. We will check it manually."},
    "ocr_note_not_receipt": {"ms": "Fail ini nampak bukan resit bayaran. Kami akan semak, atau upload resit yang betul.",
                             "en": "This file doesn't look like a payment receipt. We will check it, or upload the right one."},
    "ocr_note_failed_txn": {"ms": "Resit menunjukkan transaksi gagal atau belum selesai. Kami akan semak.",
                            "en": "The receipt shows a failed or pending transfer. We will check it."},
    "ocr_note_duplicate": {"ms": "No. rujukan ini sudah pernah digunakan. Kami akan semak.",
                           "en": "This reference number was used before. We will check it."},
    "ocr_note_old_date": {"ms": "Tarikh resit lebih awal daripada order. Kami akan semak.",
                          "en": "The receipt is dated before the order. We will check it."},
    "ocr_note_unverified": {"ms": "Amaun dibaca daripada gambar resit. Kami akan sahkan secara manual.",
                            "en": "The amount was read from the receipt image. We will confirm it manually."},
    "rcpt_rejected": {"ms": "Resit tidak diterima", "en": "Receipt not accepted"},
    "rcpt_rejected_hint": {"ms": "Sila upload resit yang betul di atas.", "en": "Please upload the correct receipt above."},
    "overpaid_amount": {"ms": "Bayaran anda melebihi jumlah order sebanyak {amt}. Kami akan hubungi anda melalui WhatsApp untuk pemulangan.",
                        "en": "You paid {amt} more than the order total. We will contact you via WhatsApp to return it."},
    "refunded_note": {"ms": "Lebihan bayaran {amt} telah dipulangkan pada {date}.",
                      "en": "The extra {amt} was returned to you on {date}."},
    "chk_title": {"ms": "Menyemak bayaran anda", "en": "Checking your payment"},
    "chk_s1": {"ms": "Memuat naik resit", "en": "Uploading receipt"},
    "chk_s2": {"ms": "Membaca resit", "en": "Reading the receipt"},
    "chk_s3": {"ms": "Mengesahkan amaun dan rujukan", "en": "Verifying amount and reference"},
    "chk_s4": {"ms": "Mengemas kini order", "en": "Updating your order"},
    "chk_wait": {"ms": "Jangan tutup atau muat semula halaman ini.", "en": "Please don't close or refresh this page."},
    "ocr_note_": {"ms": "Sedang disemak.", "en": "Being checked."},
    "uploaded_paid": {"ms": "Resit diterima dan bayaran disahkan. Terima kasih!",
                      "en": "Receipt received and payment confirmed. Thank you!"},
    "uploaded_review": {"ms": "Resit diterima. Lihat keputusan semakan di bawah.",
                        "en": "Receipt received. See the check result below."},
    # customer: edit / delete an unpaid order
    "order_actions_note": {"ms": "Belum bayar? Anda boleh ubah atau padam order ini.",
                           "en": "Not paid yet? You can change or delete this order."},
    "order_edit_back": {"ms": "Ubah order (kembali ke troli)", "en": "Edit order (back to cart)"},
    "order_edit_confirm": {"ms": "Gambar order ini akan dimasukkan semula ke troli supaya anda boleh tambah atau ubah, dan order ini dibatalkan. Teruskan?",
                           "en": "This order's photos go back into your cart so you can add or change them, and this order is removed. Continue?"},
    "order_delete": {"ms": "Padam order", "en": "Delete order"},
    "order_delete_confirm": {"ms": "Padam order ini? Ia tidak boleh dibayar lagi selepas dipadam.",
                             "en": "Delete this order? It can't be paid after it's deleted."},
    "order_deleted": {"ms": "Order telah dipadam.", "en": "The order was deleted."},
    # signed-in badge
    "acct_customer": {"ms": "Pelanggan", "en": "Customer"},
    "acct_admin": {"ms": "Admin", "en": "Admin"},
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


def from_accept_language(header: str, default: str = "ms") -> str:
    """First visit (no cookie): pick BM or English from the browser's language list."""
    for part in (header or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in ("ms", "id"):
            return "ms"
        if code == "en":
            return "en"
    return default if default in LANGS else "ms"


def safe_next(nxt: str | None) -> str:
    """Only allow same-site relative redirects."""
    nxt = nxt or "/"
    if not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt:
        return "/"
    return nxt


def t(lang: str, key: str) -> str:
    lang = lang if lang in LANGS else "ms"
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get("ms", key))


def status_label(lang: str, status: str) -> str:
    return t(lang, STATUS_KEYS.get(status, status))
