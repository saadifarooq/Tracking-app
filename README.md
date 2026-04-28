# Tracking SKU Image Lookup - Render App

This app lets employees search by tracking number, partial last 6-8 digits, barcode scan, or OCR photo scan. It returns all SKU images linked to the tracking number using the master SKU file.

## Admin features

- Admin login at `/admin`
- Upload daily PO/order file at `/admin/upload`
- Dashboard at `/admin/dashboard`
- Search logs and upload logs are saved under `UPLOAD_DIR`

## Render setup

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:app
```

Environment variables:

```text
ADMIN_PASSWORD=your-private-admin-password
SECRET_KEY=any-random-long-secret
UPLOAD_DIR=/data/uploads
```

Add a persistent disk in Render:

```text
Mount path: /data
Size: 1 GB or more
```

## Important

OCR uses Tesseract.js in the employee's phone/browser, so no extra Render server package is needed. The phone/browser needs internet access to load the OCR library.

The daily PO/order file must contain SKU and tracking number columns. The master file must contain SKU and image URL columns.
