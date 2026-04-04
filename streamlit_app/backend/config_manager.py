"""
Config Manager — Read/write automation_config.json + per-profile configs
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "automation_config.json"
STATE_PATH = PROJECT_ROOT / "automation_state.json"
CONFIGS_DIR = PROJECT_ROOT / "configs"


# ── Legacy (automation_config.json) ─────────────────────────────────

def load_config() -> Dict[str, Any]:
    """Load automation config from JSON file."""
    if not CONFIG_PATH.exists():
        return _default_config()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _default_config()


def save_config(cfg: Dict[str, Any]) -> None:
    """Save automation config to JSON file."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_state() -> Dict[str, Any]:
    """Load automation state."""
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def reset_state() -> None:
    """Delete automation state file (reprocess all)."""
    if STATE_PATH.exists():
        STATE_PATH.unlink()


# ── Per-profile config management ───────────────────────────────────

def load_all_profiles() -> List[Dict[str, Any]]:
    """Load all profile configs from configs/ directory."""
    profiles = []
    if CONFIGS_DIR.exists():
        for path in sorted(CONFIGS_DIR.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    profiles.append(json.load(f))
            except Exception:
                pass
    return profiles


def load_profile_config(profile_name: str) -> Dict[str, Any]:
    """Load a specific profile config by name."""
    path = CONFIGS_DIR / f"{profile_name}.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_profile_config(profile_name: str, cfg: Dict[str, Any]) -> None:
    """Save a profile config by name."""
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIGS_DIR / f"{profile_name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_profile_state_path(profile_name: str) -> Path:
    """Get the state file path for a profile."""
    return PROJECT_ROOT / "data" / profile_name / "state.json"


def load_profile_state(profile_name: str) -> Dict[str, Any]:
    """Load automation state for a specific profile."""
    state_path = get_profile_state_path(profile_name)
    if not state_path.exists():
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def reset_profile_state(profile_name: str) -> None:
    """Delete state file for a specific profile."""
    state_path = get_profile_state_path(profile_name)
    if state_path.exists():
        state_path.unlink()


def _default_config() -> Dict[str, Any]:
    return {
        "shared_mailbox": "",
        "shared_mailboxes": [],
        "folder_name": "Inbox",
        "rerun_folder_name": "",
        "rerun_mailbox": "",
        "skip_senders": [],
        "skip_categories": [],
        "scan_from_date": "",
        "recipient_email": "",
        "download_root": "",
        "tosend_folder": "",
        "output_copy_folder": "",
        "poll_interval_minutes": 10,
        "max_messages": 200,
        "max_files_per_email": 15,
        "max_file_size_mb": 100,
        "stage1_skip_retry_resolution_px": 8000,
        "max_image_dimension": 4096,
        "recursive": True,
        "enable_retry": True,
        "auto_start": False,
        "auto_send": False,
        "archive_full": False,
        "cleanup_download": True,
        "mark_as_processed": True,
        "mark_category_name": "AI Processed",
        "mark_category_color": "preset20",
        "nodraw_category_name": "NO DRAW",
        "nodraw_category_color": "preset1",
        "heavy_category_name": "AI HEAVY",
        "heavy_category_color": "preset4",
        "confidence_level": "LOW",
        "debug_mode": False,
        "iai_top_red_fallback": True,
        "max_retries": 3,
        "scan_dpi": 200,
        "log_max_size_mb": 1,
        "usd_to_ils_rate": 3.7,
        "selected_stages": {str(i): True for i in range(1, 10)},
        "stage_models": {},
    }
