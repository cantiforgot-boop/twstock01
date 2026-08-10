# Use official lightweight Python image
FROM python:3.10-slim

# Install system dependencies and Google Chrome (required for Selenium)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    --no-install-recommends \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/debian/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
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
