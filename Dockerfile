# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies needed for some Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /usr/src/app
USER appuser

EXPOSE 8000

CMD ["python", "-m", "gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "4"]