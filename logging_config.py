import logging
import logging.handlers
import os
from config import Config

def setup_logging():
    log_level = getattr(logging, Config.LOG_LEVEL.upper())

    # Create logs directory if it doesn't exist
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(Config.LOG_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        f'{log_dir}/gateway.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(Config.LOG_FORMAT)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Error file handler
    error_handler = logging.handlers.RotatingFileHandler(
        f'{log_dir}/errors.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(Config.LOG_FORMAT)
    error_handler.setFormatter(error_formatter)
    root_logger.addHandler(error_handler)

    # Service-specific loggers
    loggers = [
        'gateway.app',
        'gateway.grpc_client',
        'gateway.nostr_client',
        'gateway.session_manager',
        'gateway.transaction_processor',
    ]

    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(log_level)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)