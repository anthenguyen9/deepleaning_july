FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
ENV PYTHONPATH=/app/src
COPY requirements/ requirements/
RUN pip install -r requirements/requirements_web.txt
COPY . .

EXPOSE 5000
CMD ["python", "src/webapp.py"]
