"""
Prompt Loader — loads prompt text from external .txt files.

Usage:
    from src.utils.prompt_loader import load_prompt
    prompt = load_prompt("01_identify_drawing_layout")

Profile-aware usage (set once at pipeline entry):
    from src.utils.prompt_loader import set_prompts_context
    set_prompts_context("prompts/orders")
    prompt = load_prompt("01_identify_drawing_layout")  # looks in prompts/orders/ first
"""
import os
import threading
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROMPTS_DIR = os.path.join(_PROJECT_ROOT, "prompts")

# Thread-local context so scan_folder can set prompts_folder once
# and all downstream load_prompt calls pick it up automatically.
_context = threading.local()


def set_prompts_context(prompts_folder: Optional[str] = None) -> None:
    """Set the active prompts folder for the current thread.

    Args:
        prompts_folder: Relative path like "prompts/orders", or None to reset.
    """
    _context.prompts_folder = prompts_folder


def load_prompt(name: str, prompts_folder: Optional[str] = None) -> str:
    """
    Load a prompt from a .txt file and return its content.

    Resolution order:
        1. Explicit *prompts_folder* argument
        2. Thread-local context (set via set_prompts_context)
        3. Default prompts/ root directory

    Args:
        name: Prompt filename without extension, e.g. "01_identify_drawing_layout"
        prompts_folder: Optional folder path like "prompts/orders"

    Returns:
        The prompt text (stripped of leading/trailing whitespace).

    Raises:
        FileNotFoundError: if the prompt file doesn't exist.
    """
    folder = prompts_folder or getattr(_context, "prompts_folder", None)

    if folder:
        custom_path = os.path.join(_PROJECT_ROOT, folder, f"{name}.txt")
        if os.path.isfile(custom_path):
            with open(custom_path, "r", encoding="utf-8") as f:
                text = f.read().strip()
            logger.debug(f"Loaded prompt '{name}' from {folder} ({len(text)} chars)")
            return text

    # Fallback to root prompts/
    path = os.path.join(_PROMPTS_DIR, f"{name}.txt")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Prompt file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    logger.debug(f"Loaded prompt '{name}' ({len(text)} chars)")
    return text
