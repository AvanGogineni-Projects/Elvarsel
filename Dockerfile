# 3.12 for reliable ML wheels (LightGBM etc.) in later phases.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "elvarsel.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
