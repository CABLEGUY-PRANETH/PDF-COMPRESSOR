from flask import Flask, request, jsonify
import requests
import io
import base64
import os
from pypdf import PdfReader, PdfWriter

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


@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "message": "PDF Compressor API is running",
        "endpoints": {
            "POST /compress-pdf": "Compress PDF via file_url or file upload",
            "GET /health": "Health check"
        }
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/compress-pdf", methods=["POST"])
def compress_pdf():
    file_url = None
    pdf_data = None

    # JSON body
    if request.is_json:
        data = request.get_json() or {}
        file_url = data.get("file_url") or data.get("file")

    # Form field
    if not file_url and request.form:
        file_url = request.form.get("file_url")

    # Direct file upload
    if "file" in request.files:
        f = request.files["file"]
        pdf_data = f.read()

    # Download from URL if provided
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

        # Compress content streams safely
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

        # If still too large, just return compressed version
        # (Image re-encoding removed for maximum stability)
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
