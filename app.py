import csv
import os
import re
import time
from functools import lru_cache, wraps
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-in-render")

MASTER_FILE = os.environ.get("MASTER_FILE", "master.csv")
DEFAULT_PO_FILE = os.environ.get("PO_FILE", "PO_Data1.xlsx")
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/data/uploads" if Path("/data").exists() else "uploads"))
ACTIVE_PO_POINTER = UPLOAD_DIR / "active_po_file.txt"
SEARCH_LOG_FILE = UPLOAD_DIR / "search_logs.csv"
UPLOAD_LOG_FILE = UPLOAD_DIR / "upload_logs.csv"
MIN_PARTIAL_DIGITS = int(os.environ.get("MIN_PARTIAL_DIGITS", "6"))
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "50"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv"}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(value):
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.strip()


def clean_sku(value):
    return clean_text(value).upper()


def clean_tracking(value):
    s = clean_text(value)
    return re.sub(r"[^0-9A-Za-z]", "", s).upper()


def digits_only(value):
    return re.sub(r"\D", "", clean_text(value))


def find_col(columns, candidates):
    normalized = {str(c).strip().lower(): c for c in columns}
    for name in candidates:
        key = name.strip().lower()
        if key in normalized:
            return normalized[key]
    for c in columns:
        low = str(c).strip().lower()
        for name in candidates:
            if name.strip().lower() in low:
                return c
    return None


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_active_po_file():
    if ACTIVE_PO_POINTER.exists():
        saved = ACTIVE_PO_POINTER.read_text(encoding="utf-8").strip()
        if saved and Path(saved).exists():
            return saved
    return DEFAULT_PO_FILE


def set_active_po_file(path):
    ACTIVE_PO_POINTER.write_text(str(path), encoding="utf-8")
    load_data.cache_clear()


def read_table(path):
    path_str = str(path)
    ext = path_str.rsplit(".", 1)[-1].lower()

    if ext == "csv":
        return pd.read_csv(
            path_str,
            dtype=str,
            keep_default_na=False
        )

    # Excel files
    return pd.read_excel(
        path_str,
        sheet_name="Po Details",
        dtype=str,
        keep_default_na=False,
        engine="openpyxl"
    )

def now_stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def append_csv(path, fieldnames, row):
    path = Path(path)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def log_search(query, clean_query, match_type, result_count, total_matches, ok):
    try:
        append_csv(SEARCH_LOG_FILE,
            ["timestamp", "query", "clean_query", "match_type", "result_count", "total_matches", "ok", "ip", "user_agent"],
            {
                "timestamp": now_stamp(),
                "query": query,
                "clean_query": clean_query,
                "match_type": match_type,
                "result_count": result_count,
                "total_matches": total_matches,
                "ok": ok,
                "ip": request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip(),
                "user_agent": (request.headers.get("User-Agent", "") or "")[:180],
            })
    except Exception:
        pass


def log_upload(filename, saved_path, rows_loaded, status, message=""):
    try:
        append_csv(UPLOAD_LOG_FILE,
            ["timestamp", "filename", "saved_path", "rows_loaded", "status", "message"],
            {"timestamp": now_stamp(), "filename": filename, "saved_path": saved_path, "rows_loaded": rows_loaded, "status": status, "message": message})
    except Exception:
        pass


def read_recent_csv(path, limit=200):
    path = Path(path)
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        return df.tail(limit).iloc[::-1].to_dict(orient="records")
    except Exception:
        return []


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("admin_logged_in"):
            return view(*args, **kwargs)
        return redirect(url_for("admin_login"))
    return wrapped


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@lru_cache(maxsize=1)
def load_data():
    po_file = get_active_po_file()
    master = read_table(MASTER_FILE)
    po = read_table(po_file)

    master_sku_col = find_col(master.columns, ["SKU", "Seller SKU", "Sku"])
    master_img_col = find_col(master.columns, ["Primary Image URL", "Image URL", "Image", "Product Image URL"])
    master_name_col = find_col(master.columns, ["Product Name", "Item Description", "Title", "Name"])
    master_item_url_col = find_col(master.columns, ["Item Page URL", "Product URL", "URL"])

    po_sku_col = find_col(po.columns, ["SKU", "Seller SKU", "Sku"])
    tracking_col = find_col(po.columns, ["Tracking Number", "Tracking#", "Tracking ID", "Tracking", "Last Mile Tracking"])
    update_tracking_col = find_col(po.columns, ["Update Tracking Number", "Updated Tracking Number"])
    order_col = find_col(po.columns, ["Order#", "Order Number", "Customer Order Id", "Original Customer Order Id"])
    po_col = find_col(po.columns, ["PO#", "PO Number"])
    qty_col = find_col(po.columns, ["Qty", "Quantity"])
    desc_col = find_col(po.columns, ["Item Description", "Product Name", "Description"])

    required = {"master SKU": master_sku_col, "master image URL": master_img_col, "PO SKU": po_sku_col, "PO tracking number": tracking_col}
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))

    master["__sku"] = master[master_sku_col].map(clean_sku)
    master_lookup = {}
    for _, row in master.iterrows():
        sku = row["__sku"]
        if not sku:
            continue
        entry = master_lookup.setdefault(sku, {"sku": sku, "name": "", "image_urls": [], "item_url": ""})
        if master_name_col and not entry["name"]:
            entry["name"] = clean_text(row.get(master_name_col, ""))
        if master_item_url_col and not entry["item_url"]:
            entry["item_url"] = clean_text(row.get(master_item_url_col, ""))
        img = clean_text(row.get(master_img_col, ""))
        if img and img not in entry["image_urls"]:
            entry["image_urls"].append(img)

    records = []
    for _, row in po.iterrows():
        sku = clean_sku(row.get(po_sku_col, ""))
        tracking = clean_tracking(row.get(tracking_col, ""))
        update_tracking = clean_tracking(row.get(update_tracking_col, "")) if update_tracking_col else ""
        track = update_tracking or tracking
        if not sku or not track:
            continue
        digits = digits_only(track)
        master_info = master_lookup.get(sku, {})
        records.append({
            "tracking": track,
            "tracking_digits": digits,
            "sku": sku,
            "qty": clean_text(row.get(qty_col, "")) if qty_col else "",
            "po": clean_text(row.get(po_col, "")) if po_col else "",
            "order": clean_text(row.get(order_col, "")) if order_col else "",
            "description": clean_text(row.get(desc_col, "")) if desc_col else master_info.get("name", ""),
            "master_name": master_info.get("name", ""),
            "image_urls": master_info.get("image_urls", []),
            "item_url": master_info.get("item_url", ""),
            "has_image": bool(master_info.get("image_urls")),
        })

    return {"records": records, "stats": {"po_rows_loaded": len(records), "master_skus_loaded": len(master_lookup), "master_file": MASTER_FILE, "po_file": po_file, "last_loaded_at": now_stamp()}}


def group_results(records):
    grouped = {}
    for rec in records:
        tracking = rec["tracking"]
        group = grouped.setdefault(tracking, {"tracking": tracking, "po": rec.get("po", ""), "order": rec.get("order", ""), "items": []})
        item_key = (rec["sku"], rec.get("description", ""))
        if not any((x["sku"], x.get("description", "")) == item_key for x in group["items"]):
            group["items"].append({"sku": rec["sku"], "qty": rec.get("qty", ""), "description": rec.get("description") or rec.get("master_name", ""), "master_name": rec.get("master_name", ""), "image_urls": rec.get("image_urls", []), "item_url": rec.get("item_url", ""), "has_image": rec.get("has_image", False)})
    return list(grouped.values())


@app.route("/")
def index():
    return render_template("index.html", min_partial=MIN_PARTIAL_DIGITS)


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if not ADMIN_PASSWORD:
            flash("ADMIN_PASSWORD is not set in Render environment variables.", "error")
        elif password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_upload"))
        else:
            flash("Incorrect admin password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/upload", methods=["GET", "POST"])
@login_required
def admin_upload():
    if request.method == "POST":
        file = request.files.get("order_file")
        if not file or not file.filename:
            flash("Choose an order/PO file first.", "error")
            return redirect(url_for("admin_upload"))
        if not allowed_file(file.filename):
            flash("Only .xlsx, .xls, or .csv files are allowed.", "error")
            return redirect(url_for("admin_upload"))

        safe_name = secure_filename(file.filename)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        saved_path = UPLOAD_DIR / f"po_{timestamp}_{safe_name}"
        file.save(saved_path)

        try:
            old_pointer = get_active_po_file()
            set_active_po_file(saved_path)
            data = load_data()
            rows = data["stats"]["po_rows_loaded"]
            log_upload(safe_name, str(saved_path), rows, "success")
            flash(f"Daily order file uploaded successfully. Loaded {rows} searchable row(s).", "success")
        except Exception as exc:
            if 'old_pointer' in locals():
                set_active_po_file(old_pointer)
            try:
                saved_path.unlink(missing_ok=True)
            except Exception:
                pass
            log_upload(safe_name, str(saved_path), 0, "failed", str(exc))
            flash(f"Upload failed: {exc}", "error")
        return redirect(url_for("admin_upload"))

    stats = None
    error = None
    try:
        stats = load_data()["stats"]
    except Exception as exc:
        error = str(exc)
    return render_template("admin_upload.html", stats=stats, error=error)


@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    stats = None
    error = None
    try:
        stats = load_data()["stats"]
    except Exception as exc:
        error = str(exc)
    searches = read_recent_csv(SEARCH_LOG_FILE, 200)
    uploads = read_recent_csv(UPLOAD_LOG_FILE, 50)
    total_searches = len(read_recent_csv(SEARCH_LOG_FILE, 100000)) if SEARCH_LOG_FILE.exists() else 0
    successful = sum(1 for r in read_recent_csv(SEARCH_LOG_FILE, 100000) if str(r.get("ok", "")).lower() == "true") if SEARCH_LOG_FILE.exists() else 0
    return render_template("admin_dashboard.html", stats=stats, error=error, searches=searches, uploads=uploads, total_searches=total_searches, successful=successful)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/api/search")
def api_search():
    q_raw = request.args.get("q", "")
    q = clean_tracking(q_raw)
    q_digits = digits_only(q_raw)

    if not q:
        log_search(q_raw, q, "none", 0, 0, False)
        return jsonify({"ok": False, "message": "Enter or scan a tracking number.", "results": []}), 400

    try:
        data = load_data()
    except Exception as exc:
        log_search(q_raw, q, "error", 0, 0, False)
        return jsonify({"ok": False, "message": f"Data load error: {exc}", "results": []}), 500

    records = data["records"]
    exact = [r for r in records if r["tracking"] == q or (q_digits and r["tracking_digits"] == q_digits)]
    if exact:
        grouped = group_results(exact)
        log_search(q_raw, q, "exact", len(grouped), len(grouped), True)
        return jsonify({"ok": True, "match_type": "exact", "query": q_raw, "results": grouped, "total_matches": len(grouped), "stats": data["stats"]})

    if len(q_digits) >= MIN_PARTIAL_DIGITS:
        partial = [r for r in records if q_digits in r["tracking_digits"]]
    elif len(q) >= MIN_PARTIAL_DIGITS:
        partial = [r for r in records if q in r["tracking"]]
    else:
        log_search(q_raw, q, "too_short", 0, 0, False)
        return jsonify({"ok": False, "message": f"For partial search, type at least {MIN_PARTIAL_DIGITS} digits, such as the last 7 or 8 digits.", "results": [], "stats": data["stats"]}), 400

    results = group_results(partial)
    log_search(q_raw, q, "partial", min(len(results), MAX_RESULTS), len(results), bool(results))
    return jsonify({"ok": True, "match_type": "partial", "query": q_raw, "results": results[:MAX_RESULTS], "total_matches": len(results), "stats": data["stats"]})


@app.route("/api/health")
def health():
    data = load_data()
    return jsonify({"ok": True, "stats": data["stats"]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
