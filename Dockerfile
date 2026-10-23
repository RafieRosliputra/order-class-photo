FROM python:3.12-slim

# System deps:
#  - poppler-utils: pdf2image (convert PDF receipts to images)
#  - libgl1 / libglib2.0-0: PaddleOCR / OpenCV runtime
#  - tzdata: Asia/Kuala_Lumpur
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils libgl1 libglib2.0-0 tzdata curl \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Kuala_Lumpur \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies (deterministic; mirrors pyproject [project].dependencies)
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        "fastapi>=0.115.0" "uvicorn[standard]>=0.30.0" "jinja2>=3.1.4" \
        "python-multipart>=0.0.9" "itsdangerous>=2.2.0" "pydantic-settings>=2.4.0" \
        "email-validator>=2.2.0" "httpx>=0.27.0" "pillow>=10.4.0" "pdf2image>=1.17.0" \
        "qrcode>=7.4.2" "gspread>=6.1.2" "google-auth>=2.34.0" \
        "apscheduler>=3.10.4" "python-dateutil>=2.9.0"

# To enable receipt OCR inside the image, uncomment (adds ~1.5GB):
# RUN pip install --no-cache-dir paddleocr paddlepaddle

COPY . .

# Generate placeholder logo + PWA icons (replace app/static/img/logo-*.png with real ones later)
RUN python scripts/gen_icons.py || true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
