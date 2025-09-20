#!/usr/bin/env python3

"""
Database setup script for ArkRelay Gateway
This script creates all database tables and sets up the initial data.
"""

from models import create_tables
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_database():
    """Setup the database with all required tables"""
    try:
        logger.info("🗄️  Setting up database...")
        engine = create_tables()
        logger.info("✅ Database setup completed successfully!")
        logger.info("Tables created: job_logs, system_metrics, heartbeats")
        return True
    except Exception as e:
        logger.error(f"❌ Database setup failed: {e}")
        return False

if __name__ == '__main__':
    setup_database()