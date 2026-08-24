# Dockerfile for Hugging Face Spaces / Render / Cloud Deployment
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .
RUN pip install --no-cache-dir -e .

# Create non-root user for Hugging Face Spaces security standards
RUN useradd -m -u 1000 user && \
    mkdir -p /app/.keoz && \
    chown -R user:user /app

USER user

# Expose port (7860 is Hugging Face Spaces default)
EXPOSE 7860

# Start KEOZ Command Center
CMD ["python", "-m", "uvicorn", "keoz.server.app:app", "--host", "0.0.0.0", "--port", "7860"]
