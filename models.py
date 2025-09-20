from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class JobLog(Base):
    __tablename__ = 'job_logs'

    id = Column(Integer, primary_key=True)
    job_type = Column(String(50), nullable=False)
    job_id = Column(String(100), unique=True)
    status = Column(String(20), nullable=False)  # pending, running, completed, failed
    message = Column(Text)
    result_data = Column(Text)  # JSON string for results
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    duration_seconds = Column(Float)

class SystemMetrics(Base):
    __tablename__ = 'system_metrics'

    id = Column(Integer, primary_key=True)
    cpu_percent = Column(Float, nullable=False)
    memory_percent = Column(Float, nullable=False)
    memory_available_mb = Column(Float, nullable=False)
    disk_percent = Column(Float, nullable=False)
    disk_free_gb = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Heartbeat(Base):
    __tablename__ = 'heartbeats'

    id = Column(Integer, primary_key=True)
    service_name = Column(String(50), nullable=False)
    is_alive = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    message = Column(String(200))

# Database setup
def get_database_url():
    return os.getenv('DATABASE_URL', 'mysql+pymysql://user:password@mariadb:3306/arkrelay')

def create_tables():
    engine = create_engine(get_database_url())
    Base.metadata.create_all(engine)
    return engine

def get_session():
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    return Session()