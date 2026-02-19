"""
Logging utility for the newsletter automation system
"""

from loguru import logger
import sys
from pathlib import Path

def setup_logger(log_file: str = "logs/automation.log", level: str = "INFO"):
    """
    Configure the logger for the application
    
    Args:
        log_file: Path to the log file
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Remove default logger
    logger.remove()
    
    # Add console output
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True
    )
    
    # Add file output
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=level,
        rotation="10 MB",
        retention="30 days",
        compression="zip"
    )
    
    return logger

# Create default logger instance
default_logger = setup_logger()
