FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md app.py ./
COPY videocopier ./videocopier
COPY clients ./clients

RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "itsdangerous>=2.2.0" \
    "python-multipart>=0.0.12" \
    "pydantic>=2.9.0" \
    "pillow>=10.4.0" \
    "numpy>=2.0.0" \
    "opencv-python-headless>=4.10.0" \
    "rapidocr-onnxruntime>=1.4.4"

ENV PYTHONPATH=/app

RUN mkdir -p /app/fonts \
    && python -c "from videocopier.fonts import ensure_caption_font; print(ensure_caption_font().path)"

ENV PORT=8000
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["sh", "-c", "uvicorn videocopier.server:app --host 0.0.0.0 --port ${PORT}"]
