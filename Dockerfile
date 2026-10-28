FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src \
    LITELLM_LOCAL_MODEL_COST_MAP=True AGENT_MODE=live PORT=8000 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser
COPY src ./src
COPY data ./data
COPY web ./web
COPY reports ./reports
RUN chown -R appuser:appuser /app/reports
USER appuser
EXPOSE 8000
CMD ["python", "-m", "aftersales.hosting"]
