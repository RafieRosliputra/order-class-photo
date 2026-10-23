# Johor Studio — Photo Order

Server-rendered web app that lets parents browse event photos (convocation /
kindergarten), pick prints, pay **manually** (Maybank QRPay or Bank Muamalat
transfer), and upload a receipt that is **OCR-verified** against the order total.
Prints are produced by the studio and collected at school or posted — there is
**no digital download**.

> Active development is on the **`manual-payment`** branch. `main` stays clean.

---

## Features

- **Gallery** per event: flat grid with filters (school / class) and search by
  photo number / filename. Previews are served as WebP via a CSS background with
  right-click / drag-save disabled. Lightbox zoom. (No watermark — that lives in a
  separate project.)
- **Cart**: add from the gallery, then choose size + quantity (1–20) per photo,
  across all classes in one event. Per-size pricing, no minimum.
- **Login**: passwordless. A two-number code (e.g. `21 88`) is emailed; after
  verifying, the customer sets a phone number. 30-day “remember me”. 5 wrong codes
  → 15-minute lock.
- **Checkout**: pickup at the event’s school (free) or post (RM10 Peninsular /
  RM18 Sabah & Sarawak, editable per event). Post orders capture an address and a
  **Leaflet / OpenStreetMap** pin.
- **Manual payment**: the pay page shows Maybank QRPay + Bank Muamalat account +
  the exact amount. The customer uploads a receipt (PNG / JPG / PDF, multiple, 10 MB
  each). **PaddleOCR + regex** read amount, receipt no., date, time and bank
  (Maybank, CIMB, …).
  - Exact match → **auto-paid**. Short → accumulate more receipts until the total is
    met. Over → flagged, contact via WhatsApp.
  - Duplicate receipt number (checked **system-wide**) → the customer is warned and
    may force-submit; the admin is flagged.
  - OCR failure → flagged for admin review (no customer re-typing).
- **On payment**: a Google-Sheet **job list** row is appended per photo+size, and the
  full-quality originals are copied from Nextcloud into the print folder as
  `Untuk-Cetak/<event>/<SIZE>/<N>salinan/<original filename>`. A new print *session*
  (new sheet) starts when the print folder has been cleared.
- **Order tracking**: status timeline (Awaiting payment → Reviewing → Paid →
  Printing → Ready/Shipped), items, receipts, delivery + Google-Maps link, and a
  prefilled **WhatsApp** button (title + order no + email + phone).
- **Admin** (`/admin`, behind **Cloudflare Access**): events CRUD, import from
  Nextcloud, sizes/prices/postage/pay accounts/pickup, order list + filters
  (incl. flagged), receipt review (image + OCR side-by-side), mark paid / override
  amount / edit items / cancel / re-copy prints, clear trash, sales summary, audit
  log.
- **Housekeeping**: bilingual UI (BM / EN), PWA (installable), Umami analytics
  (configurable), daily SQLite backup (14-day retention), receipt originals moved to
  trash and auto-cleared after 90 days.

## Stack

FastAPI · Jinja2 (server-side) · SQLite (no ORM) · uv · PaddleOCR · Pillow /
pdf2image · httpx (Nextcloud WebDAV) · gspread · APScheduler · Leaflet.

## Project layout

```
app/
  main.py            app wiring, lifespan (init DB + scheduler)
  config.py          env settings            database.py   schema + helpers
  security.py        login codes + sessions  i18n.py       BM/EN strings
  pricing.py         deps.py (templating)    utils.py
  nextcloud.py       WebDAV client           imaging.py    previews + receipt webp
  ocr.py             PaddleOCR + regex       sheets.py     Google Sheet job list
  email_send.py      SMTP (login + paid)     printing.py   copy originals to print
  backup.py          db backup + trash sweep tasks.py      APScheduler jobs
  orders_service.py  order + receipt logic
  routers/           public, cart, auth, checkout, orders, receipts, admin
  templates/  static/
scripts/   gen_icons.py  gen_samples.py  seed_demo.py
tests/     pytest (ocr, pricing/order flow, utils)
```

## Run locally

```bash
uv sync --extra dev            # add --extra ocr to install PaddleOCR
cp .env.example .env           # fill in (SECRET_KEY, Nextcloud, SMTP, …)
uv run python scripts/gen_icons.py
uv run python scripts/seed_demo.py       # Demo Konvo event + sample photos
uv run uvicorn app.main:app --reload
# open http://localhost:8000  (gallery: /e/demo-konvo, admin: /admin)
uv run pytest
```

Without SMTP configured the login code is printed to the console (and shown on the
verify page in development), so you can log in without a mail server.

## Deploy (TrueNAS)

- **Code**: `/mnt/ssd/website-order`  ·  **Data**: `/mnt/a/storage/website/print purchase`
  (SQLite in `.../SQlite/`, plus `cache/ receipts/ trash/ backups/`).
- `docker compose up -d --build` (app only; Nextcloud and `cloudflared` run
  separately).
- **Cloudflare Tunnel** maps `shop.johorstudio.com` → `http://<host>:8000`.
- **Cloudflare Access** protects `/admin/*`. The app reads the authenticated email
  from `Cf-Access-Authenticated-User-Email` for the audit log only — it does **not**
  do its own admin auth.
- Enable OCR in the image by uncommenting the PaddleOCR line in the `Dockerfile`.

### Nextcloud
Create an app user (e.g. `galeri-bot`), share each event folder **read-only** and the
print folder **read-write**, and set `NEXTCLOUD_*` in `.env`. Event folders are
`event / class / photos`; the school name is parsed from the class folder name using
the delimiter (default `" - "`, e.g. `SKA - 3 Bestari`).

### Google Sheets
Create a service account, download its JSON to `GOOGLE_SA_JSON`, and share a Drive
folder (`GSHEET_PARENT_FOLDER_ID`) with the service-account email. Each print session
creates one sheet in that folder.

### Email
Point `SMTP_*` at a relay (Zoho / Gmail / SendGrid). `EMAIL_FROM` defaults to
`order@johorstudio.com`.

## Dynamic DuitNow QR

The pay page can show a **per-order dynamic DuitNow QR** with the amount and the
customer's phone embedded (`app/duitnow.py`). It parses the merchant's static QR
(EMVCo MPM TLV), switches Point-of-Initiation 11→12, sets Tag 54 (amount) and a
reference in Tag 62, and recomputes the Tag 63 CRC-16.

Enable it by decoding your printed static QR once and setting `DUITNOW_ENABLED=true`
and `DUITNOW_STATIC_PAYLOAD=<the EMVCo string>` in `.env`. The Bank Muamalat transfer
option is shown alongside.

> This only **pre-fills** the payer's app — it does **not** auto-confirm payment.
> Confirmation still comes from the uploaded-receipt OCR flow. Test with a few
> banks / e-wallets before relying on it in production.

## Deferred (not built here)

- **Screenshot-triggered watermark / watermarking** — moved to a separate project.

## Notes

- Money is stored in **sen** (integers); format to RM only at display.
- Photo originals are **never** cached locally — only WebP previews; originals stream
  from Nextcloud when copying to print.
- Logos: the real `logo-dark.png` / `logo-light.png` could not be fetched during
  scaffolding; placeholders are generated by `scripts/gen_icons.py`. Drop the real
  files into `app/static/img/` to replace them.
