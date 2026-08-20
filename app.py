"""
NEXT MOVE — backend server.

Flow:
  1. Customer opens "/" → fills out the form in the browser.
  2. On submit, the browser POSTs their answers as JSON to /api/generate.
  3. The server runs the matching engine, renders the PDF, saves it under
     generated/<id>.pdf, and returns {"download_url": "/download/<id>"}.
  4. The browser shows a "Your report is ready" screen with that link.

This is the piece an Etsy seller would deploy somewhere public (Render,
Railway, PythonAnywhere, a VPS...) and put the resulting URL in their Etsy
delivery message / digital download instructions. Running it here on
localhost proves the flow works end to end; going live on Etsy just means
pointing this same code at a public host instead of 127.0.0.1.
"""
import os
import uuid
import json
import subprocess
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template

from engine import build_context
from llm_interpreter import get_text_scores

HERE = Path(__file__).parent
GENERATED_DIR = HERE / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("form.html")


@app.route("/api/generate", methods=["POST"])
def generate():
    answers = request.get_json(force=True)
    if not answers:
        return jsonify({"error": "No answers received."}), 400

    report_id = uuid.uuid4().hex[:12]
    html_path = GENERATED_DIR / f"{report_id}.html"
    pdf_path = GENERATED_DIR / f"{report_id}.pdf"

    try:
        text_scores = get_text_scores(answers)  # None if no API key / offline — engine falls back
        context = build_context(answers, text_scores=text_scores)

        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(HERE)))
        template = env.get_template("report_template.html.j2")
        html_path.write_text(template.render(**context))

        subprocess.run(
            ["wkhtmltopdf", "--enable-local-file-access", str(html_path), str(pdf_path)],
            check=True, capture_output=True,
        )
    except Exception as e:
        return jsonify({"error": f"Report generation failed: {e}"}), 500
    finally:
        if html_path.exists():
            html_path.unlink()

    # Save the customer's name alongside the file for a nicer download filename
    (GENERATED_DIR / f"{report_id}.meta.json").write_text(
        json.dumps({"name": answers.get("name", "")})
    )

    return jsonify({"report_id": report_id, "download_url": f"/download/{report_id}"})


@app.route("/download/<report_id>")
def download(report_id):
    # basic sanitation — report_id is always a 12-char hex token we generated
    if not report_id.isalnum() or len(report_id) != 12:
        return "Not found.", 404

    pdf_path = GENERATED_DIR / f"{report_id}.pdf"
    if not pdf_path.exists():
        return "Report not found — it may have expired.", 404

    meta_path = GENERATED_DIR / f"{report_id}.meta.json"
    filename = "career-clarity-report.pdf"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("name"):
            safe = "".join(c for c in meta["name"] if c.isalnum() or c in " -_").strip().replace(" ", "-")
            if safe:
                filename = f"{safe}-career-clarity-report.pdf"

    return send_file(pdf_path, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
