FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=America/Sao_Paulo
# poppler-utils: pdftotext para ler extrato e fatura em PDF; curl: healthcheck.
# libreoffice-calc-nogui + python3-uno: preencher o modelo da planilha antiga (app/ods_preencher.py, com o
# /usr/bin/python3 do sistema). Só roda ao baixar a planilha e sai em seguida.
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-por curl tzdata libreoffice-calc-nogui python3-uno \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt
COPY app ./app
COPY web ./web
COPY scripts ./scripts
COPY tests ./tests
COPY pytest.ini ./
# uid do usuário do host (UID_HOST no compose): o banco e a fila de avisos ficam no home dele.
ARG UID=1000
RUN useradd --uid ${UID} --create-home --shell /usr/sbin/nologin financas
USER ${UID}
EXPOSE 8095
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD curl -fsS http://127.0.0.1:8095/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8095", "--no-access-log"]
