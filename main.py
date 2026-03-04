from flask import Flask, request, jsonify
import requests
import io
import base64
from pypdf import PdfWriter
import os

app = Flask(__name__)

TARGET_SIZE_BYTES = 45 * 1024  # 45 KB

def upload_to_temp_host(pdf_bytes: bytes, filename: str = "compressed.pdf") -> str | None:
    """Upload PDF to 0x0.st (free temp hosting) and return public URL."""
    try:
        files = {"file": (filename, pdf_bytes, "application/pdf")}
        r = requests.post("https://0x0.st", files=files, timeout=30)
        r.raise_for_status()
        url = r.text.strip()
        return url if url.startswith("http") else None
    except Exception:
        return None

@app.route("/compress-pdf", methods=["POST"])
def compress_pdf():
    """Accepts file_url in JSON or file upload. Returns compressed PDF URL."""
    file_url = None
    pdf_data = None

    if request.is_json:
        data = request.get_json() or {}
        file_url = data.get("file_url") or data.get("file")

    if not file_url and request.form:
        file_url = request.form.get("file_url")

    if "file" in request.files:
        f = request.files["file"]
        pdf_data = f.read()

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
        writer = PdfWriter(clone_document_from=pdf_stream)

        for page in writer.pages:
            page.compress_content_streams(level=9)
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)

        output = io.BytesIO()
        writer.write(output)
        size = len(output.getvalue())

        if size > TARGET_SIZE_BYTES:
            writer = PdfWriter(clone_document_from=io.BytesIO(output.getvalue()))
            for page in writer.pages:
                for img in page.images:
                    img.replace(img.image, quality=25)
            output = io.BytesIO()
            writer.write(output)
            size = len(output.getvalue())

        pdf_bytes = output.getvalue()

        # Upload to temp host to get URL (for Zapier/IRIS CRM)
        compressed_url = upload_to_temp_host(pdf_bytes, "compressed_document.pdf")

        result = {
            "success": True,
            "file_size_bytes": size,
            "filename": "compressed_document.pdf",
            "filetype": "application/pdf",
        }

        if compressed_url:
            result["compressed_pdf_url"] = compressed_url
            result["file"] = {
                "url": compressed_url,
                "filename": "compressed_document.pdf",
                "filetype": "application/pdf"
            }
        else:
            result["compressed_pdf_base64"] = base64.b64encode(pdf_bytes).decode()
            result["warning"] = "Could not upload to temp host; returning base64"

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
