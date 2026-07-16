import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def setup_logger(service_name: str) -> logging.Logger:
    """
    Standard logging configuration for Microservices.
    Writes logs simultaneously to stdout (Console) and file `/app/logs/{service_name}.log`.
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers when imported multiple times
    if logger.handlers:
        return logger

    # Standard log format
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] - %(message)s"
    )

    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File Handler (for Promtail log aggregation)
    log_dir = "/app/logs"
    if not os.path.exists(log_dir):
        # Fallback to local directory if testing without Docker volumes
        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{service_name}.log")
    
    try:
        # Limit log file to max 10MB, keep up to 3 backup files
        file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=3)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        # If no write permission to the file (CI test runs), skip file logger and use console logger only
        logger.warning(f"Could not setup file logger for {service_name} ({e}). Logging to console only.")

    return logger
