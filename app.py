from flask import Flask, request, render_template, send_file
from pdf_utils import (
    pdf_to_text_cleaned,
    extract_non_dictionary_words,
    DEFAULT_PRONUNCIATION_PATH,
)
import os
import uuid

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["pdf"]
        if file:
            file_id = str(uuid.uuid4())
            pdf_path = os.path.join(UPLOAD_FOLDER, f"{file_id}.pdf")
            txt_out  = os.path.join(UPLOAD_FOLDER, f"{file_id}.txt")
            file.save(pdf_path)

            text = pdf_to_text_cleaned(pdf_path)

            # 🔍 Optional debug output
            # print(text)

            extract_non_dictionary_words(
                text,
                dictionary_path="words.txt",
                output_txt_path=txt_out,
                pronunciation_path=DEFAULT_PRONUNCIATION_PATH,  # NEW
            )
            return send_file(txt_out, as_attachment=True)
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
