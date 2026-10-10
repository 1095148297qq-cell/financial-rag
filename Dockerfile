FROM python:3.11-slim
WORKDIR /app
COPY requirements-backend.txt .
RUN pip install --no-cache-dir -r requirements-backend.txt
RUN useradd -m appuser && chown appuser:appuser /app
COPY --chown=appuser:appuser financial_rag/ financial_rag/
COPY --chown=appuser:appuser output/questions.json output/questions.json
COPY --chown=appuser:appuser output/evaluation/ output/evaluation/
COPY --chown=appuser:appuser output/evaluation_v4/ output/evaluation_v4/
COPY --chown=appuser:appuser deploy-data/index/ data/index_v4/
COPY --chown=appuser:appuser deploy-data/models/ .cache/models/
ENV RAG_SERVER_MODE=public PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=10)"
CMD ["python","-m","uvicorn","financial_rag.server:app","--host","0.0.0.0","--port","8000","--workers","1","--no-access-log"]
