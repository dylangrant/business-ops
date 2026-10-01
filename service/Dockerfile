FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "pyyaml>=6"
WORKDIR /app
CMD ["python", "-m", "service.server"]
