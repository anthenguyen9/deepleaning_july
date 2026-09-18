FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements_web.txt .
RUN pip install -r requirements_web.txt
COPY . .

EXPOSE 5000
CMD ["python", "webapp.py"]
