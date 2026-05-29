# Tracking SKU Image Lookup — Render Web App

This app uses:
- `master.csv` as the master SKU/image file
- the active daily PO/order file uploaded by admin
- SKU as the matching identifier
- full tracking number search
- partial tracking search, including last 7–8 digits
- camera barcode scanning from employee phone/computer browser
- multiple SKU images for one tracking number

## Employee use

Employees go to the main website `/` and can:
- type the full tracking number
- type the last 7 or 8 digits
- click **Scan Label** and scan the barcode on the shipping label

## Admin daily upload

Admin goes to:

`/admin`

The admin can upload the new daily PO/order file as `.xlsx`, `.xls`, or `.csv`.

The uploaded file must include:
- a SKU column, such as `SKU` or `Seller SKU`
- a tracking column, such as `Tracking Number`, `Tracking ID`, or `Tracking`

After upload, the employee search page uses the newest file immediately.

## Render environment variables

Set these in Render under **Environment**:

- `ADMIN_PASSWORD` = your private admin password
- `SECRET_KEY` = any long random text, for example `change-this-to-a-long-random-secret`
- `UPLOAD_DIR` = `/data/uploads`
- `MIN_PARTIAL_DIGITS` = `6`
- `MAX_RESULTS` = `50`

## Important Render storage note

Daily admin uploads need persistent storage. This project includes a Render disk mounted at `/data` in `render.yaml`.

If your Render plan does not support persistent disks, the upload can be lost after a restart or redeploy. In that case, either:
- use a Render plan with persistent disk, or
- replace the PO file in GitHub and redeploy.

## Files required

Keep these files in the repo:
- `app.py`
- `requirements.txt`
- `render.yaml`
- `templates/index.html`
- `templates/admin_login.html`
- `templates/admin_upload.html`
- `master.csv`
- starting sample file: `PO_Data1.xlsx`

## Deploy to Render

1. Upload all files/folders from this zip into GitHub.
2. In Render, create a **New Web Service**.
3. Connect the GitHub repo.
4. Render should use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
5. Add the environment variables above.
6. Deploy.
7. Visit `/admin` and upload the daily order file.
