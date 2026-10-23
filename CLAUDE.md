# CLAUDE.md — johorstudio-photo-order

Guidance for AI agents (and humans) working on this repo.

## What this is
Server-rendered web app for **Johor Studio** so parents can browse event photos
(convocation / kindergarten), pick prints, pay **manually** (Maybank QRPay or Bank
Muamalat transfer), and upload a receipt that is **OCR-verified** against the order
total. Prints are produced by the studio; there is **no digital download**.

Active development happens on the **`manual-payment`** branch. `main` stays clean
(README + repo meta).

## Stack
- Python 3.12, **FastAPI**, **Jinja2** server-side templates (no SPA).
- **SQLite** (single file under `DATA_DIR/SQlite/`). Access via the thin helpers in
  `app/database.py` — no ORM.
- **uv** + `pyproject.toml` for dependencies.
- **PaddleOCR + regex** for receipts (`app/ocr.py`), optional extra `ocr`.
- **WebDAV** to Nextcloud for photo originals + print output (`app/nextcloud.py`).
- **gspread** for the Google-Sheet job list; **aiosmtplib** for email.
- Background work via FastAPI `BackgroundTasks`; schedules via APScheduler
  (daily trash sweep + DB backup).

## Conventions
- All config comes from env (`app/config.py`, pydantic-settings). Never hardcode
  secrets or paths — add a field + `.env.example` entry.
- UI is bilingual (ms/en); copy lives in `app/i18n.py`. Keep both languages in sync.
- Money is stored in **sen** (integers) in the DB; format as RM x.xx only at display.
- Photo originals are **never** cached locally — only WebP previews. Originals are
  streamed from Nextcloud when copying to the print folder.
- Admin pages (`/admin/**`) carry **no app auth**; they are protected by Cloudflare
  Access. Treat the `Cf-Access-Authenticated-User-Email` header as the admin identity
  for the audit log only.

## Run locally
```bash
uv sync --extra dev          # add --extra ocr for PaddleOCR
cp .env.example .env         # fill in
uv run uvicorn app.main:app --reload
uv run python scripts/seed_demo.py     # Demo Konvo event + sample photos
uv run pytest
```

## Model selection
No special policy — use whatever model the task warrants.

## Safety notes
- Dynamic QR generation is intentionally **not** built yet (see README “Deferred”).
- OCR can misread; exact-amount match auto-approves, everything else is flagged for
  admin. Never auto-approve on a fuzzy match.
