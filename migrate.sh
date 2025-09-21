#!/bin/bash

# Database migration script for ArkRelay Gateway
# This script loads environment variables and runs Alembic migrations

set -e

echo "🗄️  Starting database migration..."

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "📝 Loading environment variables from .env..."
    export $(cat .env | xargs)
fi

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL environment variable is not set!"
    echo "Please set DATABASE_URL in your .env file or environment variables."
    exit 1
fi

echo "🔗 Using database URL: $DATABASE_URL"

# Check if this is the first migration
if [ ! -d "alembic/versions" ] || [ -z "$(ls -A alembic/versions/)" ]; then
    echo "📋 Creating initial migration..."
    alembic revision --autogenerate -m "Initial migration"
fi

echo "⬆️  Running database migrations..."
alembic upgrade head

echo "✅ Database migration completed successfully!"