import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(name: str = "fireform", level: int = logging.INFO) -> logging.Logger:
    """
    Create and return a configured logger.

    Usage:
        from src.logger import setup_logger
        logger = setup_logger(__name__)
        logger.info("Hello from %s", __name__)
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if called more than once
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(handler)

    logger.setLevel(level)
    return logger
