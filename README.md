# NEXT MOVE — Career Clarity Report (web app)

Customer flow: opens a link → fills the form → clicks "Generate my report"
→ gets a download button for their personalized 14-page PDF.

This is a real, working Flask app — tested end to end (form submit → engine
→ PDF → download link → valid file).

## Run it locally

```
pip install -r requirements.txt
python3 app.py
```

Then open http://127.0.0.1:5050 in a browser.

(Optional) set an API key so free-text answers are read by Claude instead
of the keyword fallback:

```
export ANTHROPIC_API_KEY=sk-ant-...
python3 app.py
```

## Getting this onto Etsy

Right now this only runs on your own machine. For an Etsy buyer to actually
use it, it needs to live on a public URL you control. Simplest options,
roughly easiest first:

1. **Render.com** (free tier works for low volume) — connect this folder as
   a repo, set the start command to `python3 app.py`, it gives you a public
   `https://your-app.onrender.com` URL.
2. **Railway.app** — similar one-click deploy from a repo.
3. **PythonAnywhere** — good if you want something dead simple and don't
   need much traffic.
4. A small VPS (Hetzner, DigitalOcean) if you want full control — more
   setup, more flexibility.

Once deployed, your Etsy listing's digital download / delivery message
just needs to contain that URL. The buyer clicks it, fills the form, and
downloads their PDF directly — no manual work on your end per order.

## Things to change before going live

- **wkhtmltopdf must be installed on the host** — it's a system package,
  not a pip package (`apt install wkhtmltopdf` on most Linux hosts; check
  your platform's docs, e.g. Render's buildpacks).
- **Generated PDFs currently live forever in `generated/`.** Add a cleanup
  job (cron, or a check on each request) to delete files older than a day
  or two, or storage will grow unbounded.
- **`app.run(debug=False)` is already set**, but the built-in Flask server
  still isn't meant for real traffic — put it behind `gunicorn` or `waitress`
  for production (one line: `gunicorn -w 2 -b 0.0.0.0:5050 app:app`).
- **Add basic rate limiting / a simple order-verification step** if you
  want to make sure only people who actually paid can generate a report
  (e.g. require an order-number field that you check against a list).

## Files

- `app.py` — the server: serves the form, handles `/api/generate`, serves
  `/download/<id>`.
- `templates/form.html` — the customer-facing form.
- `engine.py`, `careers.py` — the matching engine (form answers → scored
  career matches).
- `llm_interpreter.py` — optional Claude-based reading of free-text
  answers; falls back to keyword matching if no API key is set.
- `report_template.html.j2` — the 14-page report layout, filled in per
  customer by the engine's output.
