FROM ghcr.io/astral-sh/uv:0.8.2 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache --python /usr/local/bin/python
COPY . .
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
ENTRYPOINT ["python", "pipeline.py"]
CMD ["--help"]
