FROM python:3.11-slim

# 1. Install Windows/Linux system dependencies for audio, PDF, and database packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Upgrade pip to handle large wheels smoothly
RUN pip install --no-cache-dir --upgrade pip

# 3. CRUCIAL: Install lightweight CPU-only ML packages to prevent Render OOM crashes
RUN pip install --no-cache-dir torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 --extra-index-url https://pytorch.org

# 4. Copy and install the remaining ShopAI requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your Django project files
COPY . .

# 6. Expose port 10000 (Render's default public port)
EXPOSE 10000

# 7. Start the application using Gunicorn
CMD ["gunicorn", "ShopSmartAI.wsgi:application", "--bind", "0.0.0.0:10000"]
