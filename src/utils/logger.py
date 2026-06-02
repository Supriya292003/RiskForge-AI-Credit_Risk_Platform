import logging
import os
import sys

def setup_logger(name="risk_forge_ai"):
    """Sets up a standardized logger for console logging."""
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers if logger is already set up
    if logger.handlers:
        return logger

    # Load log level from env, default to INFO
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    logger.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Format
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s:%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

# Create a default logger instance
logger = setup_logger()
