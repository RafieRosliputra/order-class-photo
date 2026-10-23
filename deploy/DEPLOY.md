# Deployment (TrueNAS SCALE + Cloudflare Tunnel)

This is how the live instance is wired on the Johor Studio TrueNAS (`m10`).

## TrueNAS
- **Code**: `/mnt/ssd/website-order` (this repo, `manual-payment` branch).
- **Data**: `/mnt/a/storage/website/print purchase/` → `SQlite/ cache/ receipts/ trash/ backups/`.
- **Image**: built on the host — `docker build -t johorstudio-photo-order:local /mnt/ssd/website-order`.
- **App**: a **Custom App** named `photo-order` (see `truenas-app.yaml`), published on host
  port **8099** → container 8000. Shows under **Apps**.
- After editing `.env`, redeploy: `midclt call app.redeploy photo-order` (or Apps → restart).
- Rebuild after a code change:
  ```
  cd /mnt/ssd/website-order && git pull
  docker build -t johorstudio-photo-order:local .
  midclt call app.redeploy photo-order
  ```

## Cloudflare (tunnel `m10`)
- Public hostname `shop.johorstudio.com` → `http://192.168.0.100:8099` (added to the tunnel ingress).
- DNS: `shop` CNAME → `<tunnel-id>.cfargotunnel.com` (proxied).
- **Access**: a self-hosted Access app protects `shop.johorstudio.com/admin`, policy allows the
  owner email. Add more emails in Zero Trust → Access → Applications.

## Fill in before going live (`/mnt/ssd/website-order/.env`)
- `NEXTCLOUD_BASE_URL` (e.g. internal `http://192.168.0.100:30027`), `NEXTCLOUD_USER`,
  `NEXTCLOUD_APP_PASSWORD`, `NEXTCLOUD_WEBDAV_ROOT`.
- `PAY_BANK_ACCOUNT_NO` (Bank Muamalat), and for dynamic QR: `DUITNOW_ENABLED=true` +
  `DUITNOW_STATIC_PAYLOAD` (decode the printed static DuitNow QR once).
- `SMTP_*` (relay) for login + payment emails.
- `GOOGLE_SA_JSON` + `GSHEET_PARENT_FOLDER_ID` for the job-list sheet.
- `UMAMI_SRC=https://ana.johorstudio.com/script.js` + `UMAMI_WEBSITE_ID` (add the site in Umami).
- Enable OCR: uncomment the PaddleOCR line in the `Dockerfile`, set `OCR_ENABLED=true`, rebuild.

## Quick test
`midclt`-run the demo seed inside the container, or create a real event at `/admin`.
