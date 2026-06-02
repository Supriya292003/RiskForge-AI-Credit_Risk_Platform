# Build stage for FastAPI Credit Risk Backend
FROM python:3.10-slim

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and artifacts
COPY src/ ./src/
COPY models/ ./models/
COPY sql/ ./sql/

# Expose port
EXPOSE 8000

# Start server
CMD ["python", "src/main.py"]
