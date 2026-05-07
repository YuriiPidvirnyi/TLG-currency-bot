FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y \
    tzdata fonts-dejavu-core fonts-liberation \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

ENV TZ=Europe/Kyiv

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY app ./app
COPY migrations ./migrations

RUN mkdir -p /data/reports
VOLUME ["/data"]

ENV DB_PATH=/data/clinic.db
ENV REPORTS_DIR=/data/reports

CMD ["python", "bot.py"]
