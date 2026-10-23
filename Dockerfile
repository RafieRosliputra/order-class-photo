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

# Install uv, then dependencies (layer-cached on lockfile)
COPY pyproject.toml ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system --no-cache -r <(uv pip compile pyproject.toml 2>/dev/null || true) || \
    pip install --no-cache-dir \
        fastapi "uvicorn[standard]" jinja2 python-multipart itsdangerous \
        pydantic-settings email-validator httpx pillow pdf2image \
        gspread google-auth aiosmtplib apscheduler python-dateutil

# To enable OCR inside the image, uncomment:
# RUN pip install --no-cache-dir paddleocr paddlepaddle

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
