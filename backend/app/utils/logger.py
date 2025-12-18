"""
应用程序的日志配置。
"""
import logging
import sys
from datetime import datetime

# 配置日志格式
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 创建日志记录器
logger = logging.getLogger("videosieve")
logger.setLevel(logging.INFO)

# 控制台处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
console_handler.setFormatter(console_formatter)

# 添加处理器
logger.addHandler(console_handler)


def get_logger(name: str = "videosieve"):
    """获取指定名称的日志记录器实例。"""
    return logging.getLogger(name)
