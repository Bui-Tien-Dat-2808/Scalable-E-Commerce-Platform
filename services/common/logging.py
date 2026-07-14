import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def setup_logger(service_name: str) -> logging.Logger:
    """
    Cấu hình Logging chuẩn cho Microservice.
    Ghi log đồng thời ra stdout (Console) và file `/app/logs/{service_name}.log`.
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)

    # Tránh duplicate handler khi import nhiều lần
    if logger.handlers:
        return logger

    # Format log chuẩn
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] - %(message)s"
    )

    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File Handler (cho Promtail gom log)
    log_dir = "/app/logs"
    if not os.path.exists(log_dir):
        # Fallback về thư mục local nếu chạy test không có Docker volume
        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{service_name}.log")
    
    try:
        # Giới hạn file tối đa 10MB, tối đa lưu 3 file backup
        file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=3)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        # Nếu không có quyền ghi file (chạy test CI), bỏ qua file logger và chỉ dùng console logger
        logger.warning(f"Could not setup file logger for {service_name} ({e}). Logging to console only.")

    return logger
