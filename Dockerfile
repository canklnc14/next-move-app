FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p generated

EXPOSE 5050
CMD gunicorn -w 2 -b 0.0.0.0:${PORT:-5050} app:app
