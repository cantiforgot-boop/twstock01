# Use official lightweight Python image
FROM python:3.10-slim

# Install system dependencies and Google Chrome stable (without deprecated apt-key)
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    --no-install-recommends \
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the Flask port (Render will override this via the PORT environment variable)
EXPOSE 5001

# Command to run Flask with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "app:app", "--timeout", "120"]
