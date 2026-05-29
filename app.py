from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import os
from werkzeug.utils import secure_filename

app = Flask(**name**)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATA = []

@app.route("/")
def index():
return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():

```
global DATA

uploaded_file = request.files.get("file")

if not uploaded_file:
    return "No file uploaded"

filename = secure_filename(uploaded_file.filename)
file_path = os.path.join(UPLOAD_FOLDER, filename)

uploaded_file.save(file_path)

try:

    # Read Excel
    df = pd.read_excel(
        file_path,
        sheet_name="Po Details",
        dtype=str,
        engine="openpyxl"
    )

    # Clean columns
    df.columns = df.columns.astype(str).str.strip()

    # Save records in memory
    DATA = df.to_dict(orient="records")

    return redirect(url_for("index"))

except Exception as e:
    return f"Upload failed: {e}"
```

@app.route("/search")
def search():

```
tracking = request.args.get("tracking", "").strip()

if not tracking:
    return "Enter tracking number"

results = []

for row in DATA:

    tracking_value = str(row.get("Tracking Number", "")).strip()

    if tracking in tracking_value:
        results.append(row)

return render_template(
    "results.html",
    results=results,
    tracking=tracking
)
```

if **name** == "**main**":
app.run(
host="0.0.0.0",
port=int(os.environ.get("PORT", 5000))
)
