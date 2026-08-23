# Supported Python runtime used by CI and production containers.
FROM python:3.12-slim

# Set working directory inside container
WORKDIR /app

# Install system dependencies (e.g. for database drivers or video processing if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port 8000
EXPOSE 8000

# Apply the tracked schema before accepting traffic.
CMD ["./entrypoint.sh"]
