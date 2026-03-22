FROM python:3.11-slim

WORKDIR /app

# System-Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python-Dependencies zuerst (Layer-Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Anwendungscode
COPY . .

# Ordner für Outputs und Logs anlegen
RUN mkdir -p Output logs

# Kein Root-User im Container
RUN useradd -m -u 1000 investapp && chown -R investapp:investapp /app
USER investapp

CMD ["python", "main.py"]
