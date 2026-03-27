FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Add SDK to path
COPY . .
RUN pip install --no-cache-dir -e /sdk

ENV PYTHONPATH=/app:/sdk

CMD ["uvicorn", "forkpoint_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
