FROM python:3.13-slim AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim

RUN groupadd --system ticketdesk && \
    useradd --system --gid ticketdesk --home-dir /app --no-create-home ticketdesk

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src ./src

RUN chown -R ticketdesk:ticketdesk /app

USER ticketdesk

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
CMD python -c "import urllib.request as u; import sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8080/api/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]