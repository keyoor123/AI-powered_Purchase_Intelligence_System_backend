import logging
import sys
from app.utils.config import settings

def setup_logger():
    """Configures application-wide logging writing exclusively to the console (stdout)."""
    # Define log level from settings
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Base logging format
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Console stream handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Configure root logger
    root_logger = logging.getLogger()
    
    # Remove existing handlers to avoid double logging in FastAPI
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # Reduce log noise from third-party libraries (e.g. PaddleOCR, urllib3)
    logging.getLogger("ppocr").setLevel(logging.WARNING)
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("Logging initialized. Running in console-only logging mode.")
