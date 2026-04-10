FROM python:3.12-slim

WORKDIR /app

# Install system deps for psutil (host metrics fallback) and ping
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ python3-dev iputils-ping espeak-ng libespeak1 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-ping-interval", "25", "--ws-ping-timeout", "60"]
