# Dockerfile ajustado
FROM python:3.12-slim

# Define diretório de trabalho
WORKDIR /app

# Atualiza pip e instala compiladores e dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e instala pacotes Python
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copia todo o projeto
COPY . .

# Aplica migrations e inicia Gunicorn
CMD ["sh", "-c", "python manage.py migrate && gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120"]