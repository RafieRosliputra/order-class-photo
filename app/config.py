"""Application configuration, loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Johor Studio"
    app_env: str = "production"
    secret_key: str = "dev-insecure-change-me"
    base_url: str = "http://localhost:8000"
    timezone: str = "Asia/Kuala_Lumpur"
    default_lang: str = "ms"

    # Paths
    data_dir: str = "./data"
    sqlite_path: str = "./data/db/app.sqlite3"

    # Nextcloud
    nextcloud_base_url: str = ""
    nextcloud_user: str = ""
    nextcloud_app_password: str = ""
    nextcloud_webdav_root: str = "/remote.php/dav/files/galeri-bot"
    nextcloud_print_folder: str = "Untuk-Cetak"

    # Payment
    pay_qrpay_bank: str = "Maybank"
    pay_qrpay_image: str = ""
    pay_bank_name: str = "Bank Muamalat"
    pay_bank_account_name: str = "PROMEDIA CREATIVE SOLUTIONS"
    pay_bank_account_no: str = ""

    # Dynamic DuitNow QR (generated per order from the static merchant payload)
    duitnow_enabled: bool = False
    duitnow_static_payload: str = ""   # EMVCo TLV string decoded from the static QR
    duitnow_ref_subtag: str = "05"     # Tag 62 subtag for the reference (05 = Reference Label)

    # Postage (RM)
    postage_west: float = 10.0
    postage_east: float = 18.0

    # Receipt / OCR
    receipt_max_mb: int = 10
    receipt_webp_quality: int = 50
    trash_retention_days: int = 90
    ocr_enabled: bool = True

    # Google Sheets
    google_sa_json: str = ""
    gsheet_parent_folder_id: str = ""

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    email_from: str = "Johor Studio <order@johorstudio.com>"

    # WhatsApp
    whatsapp_number: str = "60127983745"

    # Login / sessions
    login_code_ttl_seconds: int = 600
    login_resend_seconds: int = 120
    login_max_attempts: int = 5
    login_lock_minutes: int = 15
    session_days: int = 30

    # Admin
    admin_email_header: str = "Cf-Access-Authenticated-User-Email"

    # Analytics
    umami_src: str = ""
    umami_website_id: str = ""

    # Backups
    backup_keep_days: int = 14

    # --- derived helpers ---
    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def cache_dir(self) -> Path:
        return self.data_path / "cache"

    @property
    def receipts_dir(self) -> Path:
        return self.data_path / "receipts"

    @property
    def trash_dir(self) -> Path:
        return self.data_path / "trash"

    @property
    def backups_dir(self) -> Path:
        return self.data_path / "backups"

    def ensure_dirs(self) -> None:
        for p in (
            Path(self.sqlite_path).parent,
            self.cache_dir,
            self.cache_dir / "previews",
            self.cache_dir / "thumbs",
            self.receipts_dir,
            self.trash_dir,
            self.backups_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)

    @property
    def is_dev(self) -> bool:
        return self.app_env.lower() in ("dev", "development", "local")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
