"""Logging configuration"""
import logging
import sys
from pathlib import Path

# Create logs directory
LOG_DIR = Path("logs")
try:
    LOG_DIR.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(LOG_DIR / "bot.log")
    handlers = [file_handler, logging.StreamHandler(sys.stdout)]
except (PermissionError, OSError):
    # If can't write to file, just use stdout
    handlers = [logging.StreamHandler(sys.stdout)]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)

logger = logging.getLogger("vpn_bot")
