FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y \
    tzdata \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

ENV TZ=Europe/Kyiv

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
