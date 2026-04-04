"""
DocumentPipeline — The ONE generic document processing engine.
===============================================================

Behavior is 100% driven by the profile config JSON.
All document types (quotes, orders, invoices, delivery, complaints)
run through this SAME class with different configurations.

Usage:
    python run_pipeline.py --profile quotes
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable

from src.core.cost_tracker import CostTracker
from src.utils.logger import get_logger

logger = get_logger(__name__)


def load_profile(profile_name: str, configs_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load a profile config JSON by name."""
    if configs_dir is None:
        configs_dir = Path(__file__).resolve().parent.parent / "configs"
    path = configs_dir / f"{profile_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Profile config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all_profiles(configs_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all profile configs from the configs directory."""
    if configs_dir is None:
        configs_dir = Path(__file__).resolve().parent.parent / "configs"
    profiles = []
    if configs_dir.exists():
        for path in sorted(configs_dir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    profiles.append(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to load profile {path.name}: {e}")
    return profiles


class DocumentPipeline:
    """
    Generic document processing engine. One class handles ALL document types.
    Behavior is 100% driven by the profile config.
    """

    def __init__(
        self,
        profile: Dict[str, Any],
        status_callback: Optional[Callable[[str], None]] = None,
    ):
        self.profile = profile
        self.name = profile["profile_name"]
        self.display_name = profile.get("display_name", self.name)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._status_callback = status_callback or (lambda msg: None)
        self.cost_tracker = CostTracker()
        self.log_file = Path(profile.get("log_file", f"logs/{self.name}_log.jsonl"))

        # Ensure folders exist
        folders = profile.get("folders", {})
        for key in ("download", "output", "archive", "to_send"):
            folder = folders.get(key, "")
            if folder:
                Path(folder).mkdir(parents=True, exist_ok=True)

        # AI engine based on profile
        ai_config = profile.get("ai_engine", {})
        engine_type = ai_config.get("type", "vision")

        if engine_type == "vision":
            from engine.ai_engines.vision_engine import VisionEngine
            self.ai = VisionEngine(ai_config, self.cost_tracker)
        elif engine_type == "document_intelligence":
            from engine.ai_engines.di_engine import DIEngine
            self.ai = DIEngine(ai_config, self.cost_tracker)
        else:
            raise ValueError(f"Unknown ai_engine type: {engine_type}")

        # Validator based on profile
        validation_config = profile.get("validation", {})
        if validation_config.get("use_sql_server"):
            from engine.validators.sql_validator import SQLValidator
            self.validator = SQLValidator(validation_config)
        else:
            from engine.validators.internal_validator import InternalValidator
            self.validator = InternalValidator(validation_config)

        # Output manager
        from engine.output_manager import OutputManager
        self.outputs = OutputManager(
            profile.get("output", {}),
            profile.get("folders", {}),
            self.name,
        )

        # Email connector — lazy init
        self._email_helper = None

    def _status(self, msg: str) -> None:
        """Send status message to callback and logger."""
        full_msg = f"[{self.display_name}] {msg}"
        logger.info(full_msg)
        self._status_callback(full_msg)

    def _get_email_helper(self):
        """Lazy-init the Graph API email helper."""
        if self._email_helper is None:
            from src.services.email.graph_helper import GraphAPIHelper
            email_cfg = self.profile.get("email", {})
            self._email_helper = GraphAPIHelper(
                shared_mailbox=email_cfg.get("shared_mailbox", ""),
            )
        return self._email_helper

    def _log_entry(self, entry: Dict[str, Any]) -> None:
        """Append a JSON line to the profile's log file."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        entry["profile"] = self.name
        entry["timestamp"] = datetime.now().isoformat()
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Core processing ─────────────────────────────────────────────

    def run_once(self) -> Dict[str, Any]:
        """Execute a single processing cycle. Returns summary dict."""
        self._status("מתחיל מחזור עיבוד...")
        email_cfg = self.profile.get("email", {})
        ai_type = self.profile["ai_engine"]["type"]

        if ai_type == "vision":
            return self._run_once_vision()
        elif ai_type == "document_intelligence":
            return self._run_once_di()
        else:
            raise ValueError(f"Unknown engine type: {ai_type}")

    def _run_once_vision(self) -> Dict[str, Any]:
        """Vision-based processing — wraps existing AutomationRunner logic."""
        from automation_runner import AutomationRunner
        from streamlit_app.backend.config_manager import CONFIG_PATH, get_profile_state_path

        # For quotes profile — delegate to existing AutomationRunner
        # which already handles email download, classification, extraction,
        # B2B output, and email sending.
        if self.name == "quotes":
            quotes_state = get_profile_state_path("quotes")
            quotes_state.parent.mkdir(parents=True, exist_ok=True)
            runner = AutomationRunner(CONFIG_PATH, quotes_state, self._status)
            runner.run_once()
            self._status("מחזור הושלם (quotes via AutomationRunner)")
            return {"status": "ok", "profile": self.name}

        # For other vision profiles (orders, complaints) — same engine,
        # different config. We adapt the automation_config on the fly.
        config_path = self._build_compat_config()
        state_path = Path(f"data/{self.name}/state.json")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        runner = AutomationRunner(config_path, state_path, self._status)
        runner.run_once()
        self._status(f"מחזור הושלם ({self.name})")
        return {"status": "ok", "profile": self.name}

    def _run_once_di(self) -> Dict[str, Any]:
        """Document Intelligence based processing — for invoices/delivery."""
        self._status("Document Intelligence processing — not yet implemented")
        # Phase 3 will implement this fully
        return {"status": "not_implemented", "profile": self.name}

    def _build_compat_config(self) -> Path:
        """Build a temporary automation_config.json compatible with
        the existing AutomationRunner from the profile config."""
        email_cfg = self.profile.get("email", {})
        folders_cfg = self.profile.get("folders", {})
        ai_cfg = self.profile.get("ai_engine", {})
        output_cfg = self.profile.get("output", {})
        proc_cfg = self.profile.get("processing", {})
        sched_cfg = self.profile.get("scheduler", {})

        compat = {
            "shared_mailbox": email_cfg.get("shared_mailbox", ""),
            "shared_mailboxes": email_cfg.get("shared_mailboxes", []),
            "folder_name": email_cfg.get("inbox_folder", "Inbox"),
            "rerun_folder_name": email_cfg.get("rerun_folder_name", ""),
            "rerun_mailbox": email_cfg.get("rerun_mailbox", ""),
            "skip_senders": email_cfg.get("skip_senders", []),
            "skip_categories": email_cfg.get("skip_categories", []),
            "scan_from_date": email_cfg.get("scan_from_date", ""),
            "recipient_email": output_cfg.get("send_to", ""),
            "download_root": folders_cfg.get("download", ""),
            "tosend_folder": folders_cfg.get("to_send", ""),
            "output_copy_folder": folders_cfg.get("archive", ""),
            "poll_interval_minutes": email_cfg.get("scan_interval_minutes", 5),
            "max_messages": email_cfg.get("max_messages_per_cycle", 10),
            "max_files_per_email": email_cfg.get("max_files_per_email", 20),
            "max_file_size_mb": email_cfg.get("max_file_size_mb", 100),
            "stage1_skip_retry_resolution_px": ai_cfg.get("stage1_skip_retry_resolution_px", 8000),
            "max_image_dimension": ai_cfg.get("max_image_dimension", 4096),
            "recursive": proc_cfg.get("recursive", True),
            "enable_retry": ai_cfg.get("enable_image_retry", False),
            "auto_start": False,
            "auto_send": output_cfg.get("auto_send", True),
            "archive_full": proc_cfg.get("archive_full", False),
            "cleanup_download": proc_cfg.get("cleanup_download", True),
            "mark_as_processed": proc_cfg.get("mark_as_processed", True),
            "mark_category_name": email_cfg.get("category_processed", "AI Processed"),
            "mark_category_color": email_cfg.get("category_processed_color", "preset20"),
            "nodraw_category_name": email_cfg.get("category_error", "NO DRAW"),
            "nodraw_category_color": email_cfg.get("category_error_color", "preset1"),
            "heavy_category_name": email_cfg.get("category_heavy", "AI HEAVY"),
            "heavy_category_color": email_cfg.get("category_heavy_color", "preset4"),
            "confidence_level": output_cfg.get("b2b_confidence_level", "HIGH"),
            "debug_mode": proc_cfg.get("debug_mode", False),
            "iai_top_red_fallback": ai_cfg.get("iai_top_red_fallback", True),
            "max_retries": ai_cfg.get("max_retries", 3),
            "scan_dpi": ai_cfg.get("scan_dpi", 200),
            "log_max_size_mb": 1,
            "usd_to_ils_rate": 3.7,
            "selected_stages": {str(s): True for s in ai_cfg.get("stages", [])},
            "stage_models": ai_cfg.get("stage_models", {}),
            "scheduler_enabled": sched_cfg.get("enabled", False),
            "scheduler_regular_from": sched_cfg.get("regular_from", "07:00"),
            "scheduler_regular_to": sched_cfg.get("regular_to", "19:45"),
            "scheduler_heavy_from": sched_cfg.get("heavy_from", ""),
            "scheduler_heavy_to": sched_cfg.get("heavy_to", ""),
            "scheduler_interval_minutes": sched_cfg.get("interval_minutes", 5),
            "scheduler_report_folder": sched_cfg.get("report_folder", ""),
        }

        compat_path = Path(f"data/{self.name}/_compat_config.json")
        compat_path.parent.mkdir(parents=True, exist_ok=True)
        with open(compat_path, "w", encoding="utf-8") as f:
            json.dump(compat, f, ensure_ascii=False, indent=2)
        return compat_path

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start continuous processing loop in background thread."""
        if self._thread and self._thread.is_alive():
            self._status("כבר רץ")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name=f"pipeline-{self.name}")
        self._thread.start()
        self._status("התחיל לרוץ")

    def stop(self) -> None:
        """Stop the continuous loop gracefully."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=30)
        self._status("נעצר")

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        """Continuous polling loop."""
        interval = self.profile.get("email", {}).get("scan_interval_minutes", 5) * 60
        while not self._stop_event.is_set():
            try:
                result = self.run_once()
                self._log_entry(result)
            except Exception as e:
                logger.exception(f"[{self.name}] Error in processing cycle")
                self._status(f"שגיאה: {e}")
                self._log_entry({"status": "error", "error": str(e)})
            self._stop_event.wait(interval)
