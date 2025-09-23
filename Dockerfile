# Syntax Prime V2 - Production Dockerfile for Railway Deployment
# Fixed with correct Debian Trixie package names

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for file processing and OCR
RUN apt-get update && apt-get install -y \
    # Essential build tools
    gcc \
    g++ \
    # For python-magic file type detection
    libmagic1 \
    # For OpenCV image processing (correct Debian Trixie packages)
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1-mesa-dri \
    libglu1-mesa \
    # For OCR with pytesseract
    tesseract-ocr \
    tesseract-ocr-eng \
    # For PDF processing
    poppler-utils \
    # For image processing optimization
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libpng-dev \
    # Additional dependencies for OpenCV
    libgtk-3-0 \
    # FFmpeg libraries (correct Trixie package names)
    libavcodec61 \
    libavformat61 \
    libswscale8 \
    libavutil59 \
    # Cleanup to reduce image size
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app
USER app

# Set user-specific paths
ENV PATH="/home/app/.local/bin:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"

# Copy requirements first for Docker layer caching
COPY --chown=app:app requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application code
COPY --chown=app:app . .

# Create necessary directories with proper permissions
RUN mkdir -p /home/app/uploads /home/app/logs /home/app/.cache

# Set environment variables for Railway
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app:$PYTHONPATH"
ENV HOST=0.0.0.0
ENV PORT=${PORT:-8000}

# Expose the port (Railway will set the PORT environment variable)
EXPOSE $PORT

# Health check for Railway
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:${PORT:-8000}/health')"

# Production startup command
CMD uvicorn app:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers 1 \
    --loop uvloop \
    --http httptools \
    --log-level info \
    --access-log \
    --no-server-header
