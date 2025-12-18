"""
Logging configuration for the application.
"""
import logging
import sys
from datetime import datetime

# Configure logging format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Create logger
logger = logging.getLogger("videosieve")
logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
console_handler.setFormatter(console_formatter)

# Add handlers
logger.addHandler(console_handler)


def get_logger(name: str = "videosieve"):
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)
