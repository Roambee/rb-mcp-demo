FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Set environment variables for server deployment
ENV ENVIRONMENT=production
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV HOST=0.0.0.0
ENV PORT=8000

# Expose port
EXPOSE 8000


# Run the application with server-friendly settings
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000", "--log-level", "INFO"]
