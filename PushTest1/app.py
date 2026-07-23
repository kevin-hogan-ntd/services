"""
Run with:  python app.py
• GET  /sheet   → raw JSON rows from Google Sheets (for JS table)
• POST /upload  → accept a PDF, return annotated-words text file
• GET  /        → simple HTML page that shows sheet + PDF-upload form
"""
import os, uuid
from flask import (
    Flask, request, jsonify, render_template, send_file
)
from google.oauth2 import service_account
from googleapiclient.discovery import build

from pdf_utils import (
    pdf_to_text_cleaned,
    extract_non_dictionary_words,
    DEFAULT_PRONUNCIATION_PATH,
)

# ----------------------------------------------------------------------
# 0.  ---  FLASK / FOLDERS  --------------------------------------------
# ----------------------------------------------------------------------
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ----------------------------------------------------------------------
# 1.  ---  GOOGLE SHEETS CONFIG  ---------------------------------------
# ----------------------------------------------------------------------
SERVICE_ACCOUNT_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SPREADSHEET_ID = "1o_LfUI3FaNH_ZGJ7iMAsOSJw1Sw3z12n7nLSXE60LKs"
RANGE_NAME = "Sheet1!A:D"     # includes columns C & D

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)

def fetch_sheet_rows_and_pronunciations():
    """Return (rows, {word_lower: pron_from_col_D})."""
    service = build("sheets", "v4", credentials=credentials)
    result  = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME)
        .execute()
    )
    rows = result.get("values", [])
    pron_map = {}
    # assume row 0 is header
    for r in rows[1:]:
        if len(r) >= 4:
            word = r[2].strip().lower()
            pron = r[3].strip()
            if word:
                pron_map[word] = pron
    return rows, pron_map

# ----------------------------------------------------------------------
# 2.  ---  ROUTES  ------------------------------------------------------
# ----------------------------------------------------------------------
@app.route("/sheet")
def sheet_json():
    rows, _ = fetch_sheet_rows_and_pronunciations()
    return jsonify(rows)

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_pdf():
    file = request.files.get("pdf")
    if not file:
        return "No PDF supplied", 400

    file_id  = str(uuid.uuid4())
    pdf_path = os.path.join(UPLOAD_FOLDER, f"{file_id}.pdf")
    txt_out  = os.path.join(UPLOAD_FOLDER, f"{file_id}.txt")
    file.save(pdf_path)

    text = pdf_to_text_cleaned(pdf_path)
    _, sheet_pron = fetch_sheet_rows_and_pronunciations()

    extract_non_dictionary_words(
        text,
        dictionary_path="words.txt",
        output_txt_path=txt_out,
        pronunciation_path=DEFAULT_PRONUNCIATION_PATH,
        extra_pronunciations=sheet_pron,     # ← NEW
    )
    return send_file(txt_out, as_attachment=True)

# ----------------------------------------------------------------------
if __name__ == "__main__":
    # listen on 0.0.0.0 so Render/Glitch/etc. can see it; change port as you like
    app.run(host="0.0.0.0", port=10000, debug=True)

