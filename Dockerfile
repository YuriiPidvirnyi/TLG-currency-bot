FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    wget curl \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

COPY bot.py .
COPY take_fresh_screenshot.py .

CMD ["python", "bot.py"]
