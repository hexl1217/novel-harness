FROM python:3.12-slim

WORKDIR /app

RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY rag/requirements.txt rag/requirements.txt
RUN pip install --no-cache-dir -r rag/requirements.txt

COPY pyproject.toml .
COPY rag/ rag/
COPY .harness/ .harness/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 3456

CMD ["python", "rag/scripts/query.py", "--server"]
