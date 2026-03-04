from flask import Flask, request, jsonify, send_file
import requests
import io
import base64
import os
import uuid
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)

UPLOAD_FOLDER = "/tmp"
TARGET_SIZE_BYTES = 45 * 1024  # 45 KB


@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "message": "PDF Compressor API is running",
        "endpoints": {
            "POST /compress-pdf": "Compress PDF via file_url or file upload",
            "GET /download/<filename>": "Download compressed PDF",
            "GET /health": "Health check"
        }
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True)


@app.route("/compress-pdf", methods=["POST"])
def compress_pdf():
    file_url = None
    pdf_data = None

    if request.is_json:
        data = request.get_json() or {}
        file_url = data.get("file_url") or data.get("file")

    if not file_url and request.form:
        file_url = request.form.get("file_url")

    if "file" in request.files:
        pdf_data = request.files["file"].read()

    if file_url and not pdf_data:
        try:
            resp = requests.get(file_url, timeout=30)
            resp.raise_for_status()
            pdf_data = resp.content
        except Exception as e:
            return jsonify({"error": str(e), "success": False}), 400

    if not pdf_data:
        return jsonify({
            "error": "Provide file_url in JSON or upload file",
            "success": False
        }), 400

    try:
        pdf_stream = io.BytesIO(pdf_data)
        reader = PdfReader(pdf_stream)
        writer = PdfWriter()

        for page in reader.pages:
            try:
                page.compress_content_streams()
            except Exception:
                pass
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        pdf_bytes = output.getvalue()
        size = len(pdf_bytes)

        # Save file temporarily
        unique_name = f"{uuid.uuid4().hex}.pdf"
        file_path = os.path.join(UPLOAD_FOLDER, unique_name)

        with open(file_path, "wb") as f:
            f.write(pdf_bytes)

        public_url = request.host_url + "download/" + unique_name

        return jsonify({
            "success": True,
            "file_size_bytes": size,
            "compressed_pdf_url": public_url,
            "filename": unique_name
        })

    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
