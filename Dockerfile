FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --extra web --no-dev --frozen

ENV PATH="/app/.venv/bin:$PATH" \
    DVR_JOBS_DIR=/data/jobs \
    JOB_TTL_HOURS=24

RUN mkdir -p /data/jobs
VOLUME /data/jobs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

# --workers 1 is REQUIRED, not a placeholder: the job store is a single
# in-process dict. >1 uvicorn worker would split jobs across processes that
# can't see each other's state (GET /api/jobs/{id} would 404 for jobs
# started on a different worker). Don't change without first moving job
# state to Redis/DB.
CMD ["uvicorn", "dvr_noise_cutter.web.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
