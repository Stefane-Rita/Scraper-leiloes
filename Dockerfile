FROM python:3.13-slim

# Install Chromium system dependencies
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libx11-6 \
    libxrandr2 \
    libxinerama1 \
    libxi6 \
    libxext6 \
    libxcursor1 \
    libxss1 \
    libxcomposite1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install Chromium and run the application
CMD python -m playwright install chromium && python main.py
