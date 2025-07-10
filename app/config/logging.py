import logging
import logging.config
import sys
from typing import Dict, Any
import os
from logging.handlers import RotatingFileHandler


def get_logging_config(debug: bool = False) -> Dict[str, Any]:
    """Get logging configuration dictionary"""
    log_level = "DEBUG" if debug else "INFO"
    # Use absolute path for log file
    log_file_path = os.path.abspath(os.path.join("data", "logs", "app.log"))
    
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "detailed",
                "filename": log_file_path,
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf-8",  # Explicitly set UTF-8 encoding
            },
        },
        "loggers": {
            "app": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.error": {
                "level": "INFO",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["console"],
        },
    }


def setup_logging(debug: bool = False) -> None:
    """Setup application logging"""
    # Create logs directory if it doesn't exist
    os.makedirs("data/logs", exist_ok=True)
    
    # Fix Windows console encoding for Unicode support
    # (Removed reconfigure logic to avoid linter errors)
    
    # Configure logging
    config = get_logging_config(debug)
    logging.config.dictConfig(config)
    
    # Get logger for this module
    logger = logging.getLogger(__name__)
    logger.info("Logging configuration initialized")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module"""
    return logging.getLogger(f"app.{name}")

# Ensure log directory exists
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'clipper_backend.log')

LOG_LEVEL = logging.INFO

formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(name)s - %(message)s')

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
file_handler.setFormatter(formatter)
file_handler.setLevel(LOG_LEVEL)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(LOG_LEVEL)

root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)
if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
    root_logger.addHandler(file_handler)
if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
    root_logger.addHandler(console_handler) 