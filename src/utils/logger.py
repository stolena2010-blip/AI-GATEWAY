"""
Logging configuration for DrawingAI Pro
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)


class GUICallbackHandler(logging.Handler):
    def __init__(self, callback, level=logging.INFO):
        super().__init__(level)
        self._callback = callback

    def emit(self, record):
        try:
            self._callback(self.format(record))
        except Exception:
            self.handleError(record)


class _ProfileFilter(logging.Filter):
    """Injects the current thread's profile name into log records.
    If a profile is registered (via automation_runner._thread_profile_names),
    adds '[PROFILE] ' prefix to the module name for clear identification."""

    def filter(self, record):
        try:
            from automation_runner import _get_current_profile_name
            pname = _get_current_profile_name()
            if pname:
                record.name = f"{pname}:{record.name}"
        except Exception:
            pass
        return True


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[Path] = None,
    console_output: bool = True,
    gui_callback: Optional[Callable[[str], None]] = None,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """
    Setup logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Optional logs directory path
        console_output: Whether to output to console
        gui_callback: Optional callback for GUI log messages
        max_bytes: Maximum size in bytes for each log file
        backup_count: Number of rotated backup files to keep
    """
    # Convert level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()

    # Profile-name filter (injects thread's profile into log name)
    profile_filter = _ProfileFilter()
    
    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.addFilter(profile_filter)
        
        console_formatter = ColoredFormatter(
            '%(asctime)s │ %(name)-36s │ %(levelname)-8s │ %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # File handler (rotating)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"drawingai_{datetime.now().strftime('%Y%m%d')}.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        file_handler.addFilter(profile_filter)
        
        file_formatter = logging.Formatter(
            '%(asctime)s │ %(name)-36s │ %(levelname)-8s │ %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # GUI callback handler
    if gui_callback:
        gui_handler = GUICallbackHandler(gui_callback, level=numeric_level)
        gui_handler.addFilter(profile_filter)
        gui_handler.setFormatter(logging.Formatter('%(asctime)s │ %(name)-36s │ %(levelname)-8s │ %(message)s', datefmt='%H:%M:%S'))
        root_logger.addHandler(gui_handler)

    # Quiet noisy third-party libraries
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("msal").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get logger instance
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def create_log_file(log_dir: Path) -> Path:
    """
    Create log file path with timestamp
    
    Args:
        log_dir: Output folder for logs
    
    Returns:
        Log file path
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"drawingai_{datetime.now().strftime('%Y%m%d')}.log"
