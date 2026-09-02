from loguru import logger
import sys
import os

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logger.remove()
logger.add(sys.stdout, level=LOG_LEVEL, colorize=True,
           format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan> - <level>{message}</level>")
logger.add("logs/collector.log", rotation="10 MB", retention="7 days", level=LOG_LEVEL)

__all__ = ["logger"]
