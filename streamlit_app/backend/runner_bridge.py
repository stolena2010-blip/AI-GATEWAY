"""
Runner Bridge — Wraps AutomationRunner for Streamlit session_state
"""
import json
import re
import threading
import time
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Optional, Callable, Dict, Any

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from automation_runner import AutomationRunner
from streamlit_app.backend.config_manager import CONFIG_PATH, CONFIGS_DIR, STATE_PATH, get_profile_state_path

# ── Ensure Python loggers write to logs/ (same as Tkinter entry points) ──
from src.utils.logger import setup_logging as _setup_logging
_setup_logging(log_level="INFO", log_dir=PROJECT_ROOT / "logs")


# ── Process-level singletons — one RunnerBridge per profile ──────────
_singleton_lock = threading.Lock()
_instances: Dict[str, "RunnerBridge"] = {}


def get_runner_bridge(profile_name: str = "quotes") -> "RunnerBridge":
    """Return the RunnerBridge singleton for the given profile."""
    with _singleton_lock:
        if profile_name not in _instances:
            _instances[profile_name] = RunnerBridge(profile_name=profile_name)
        return _instances[profile_name]


class RunnerBridge:
    """Thread-safe wrapper around AutomationRunner for Streamlit."""

    def __init__(self, profile_name: str = "quotes", status_callback: Optional[Callable[[str], None]] = None) -> None:
        self._profile_name = profile_name
        self._status_callback = status_callback or (lambda msg: None)
        self._state_path = get_profile_state_path(profile_name)
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        # Use per-profile config if it exists, otherwise fall back to legacy
        _profile_cfg = CONFIGS_DIR / f"{profile_name}.json"
        self._config_path = _profile_cfg if _profile_cfg.exists() else CONFIG_PATH
        self._runner = AutomationRunner(self._config_path, self._state_path, self._on_status)
        self._log_lines: list[str] = []
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()  # prevents concurrent runs
        self.is_running = False
        self.is_busy = False  # True during run_once / run_heavy
        self._busy_run_type = ""  # "regular" | "heavy" during one-shot
        self._last_run_type = ""   # persists after run finishes
        self._last_email_count = 0  # total emails from last run
        # Scheduler
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None
        self.scheduler_active = False
        self._next_run_time: Optional[datetime] = None

    def _on_status(self, text: str) -> None:
        with self._lock:
            self._log_lines.append(text)
            # Keep only last 5000 lines
            if len(self._log_lines) > 5000:
                self._log_lines = self._log_lines[-5000:]
        if self._status_callback:
            self._status_callback(text)

    @property
    def is_loop_alive(self) -> bool:
        """Check if the runner's internal loop thread is actually alive."""
        t = getattr(self._runner, '_thread', None)
        return t is not None and t.is_alive()

    def start(self) -> bool:
        """Start the continuous loop. Returns False if a one-shot run is active."""
        if self.is_busy:
            self._on_status("⚠️ ריצה חד-פעמית עדיין פעילה — לא ניתן להפעיל לולאה")
            return False
        if not self.is_running:
            self._runner.start()
            self.is_running = True
        return True

    def stop(self) -> None:
        if self.is_running or self.is_loop_alive:
            self._runner.stop()
            self.is_running = False

    def can_start_run(self) -> bool:
        """Return True if no run is currently in progress."""
        return not self.is_busy and not self.is_running

    def run_once(self) -> bool:
        """Start a regular one-shot run. Returns False if another run is active."""
        if self.is_loop_alive:
            self._on_status("⚠️ לולאה רצה ברקע — עוצר לפני ריצה חד-פעמית")
            self.stop()
        if not self._run_lock.acquire(blocking=False):
            self._on_status("⚠️ ריצה כבר פעילה — לא ניתן להריץ במקביל")
            return False
        self.is_busy = True
        self._busy_run_type = "regular"
        def _do():
            try:
                self._runner.run_once()
            finally:
                self._last_run_type = "regular"
                self.is_busy = False
                self._busy_run_type = ""
                self._run_lock.release()
        threading.Thread(target=_do, daemon=True).start()
        return True

    def run_heavy(self) -> bool:
        """Start a heavy one-shot run. Returns False if another run is active."""
        if self.is_loop_alive:
            self._on_status("⚠️ לולאה רצה ברקע — עוצר לפני ריצה כבדה")
            self.stop()
        if not self._run_lock.acquire(blocking=False):
            self._on_status("⚠️ ריצה כבר פעילה — לא ניתן להריץ במקביל")
            return False
        self.is_busy = True
        self._busy_run_type = "heavy"
        def _do():
            try:
                self._runner.run_heavy()
            finally:
                self._last_run_type = "heavy"
                self.is_busy = False
                self._busy_run_type = ""
                self._run_lock.release()
        threading.Thread(target=_do, daemon=True).start()
        return True

    # ── Scheduler ──────────────────────────────────────────────────

    @staticmethod
    def _time_in_range(now_t: dt_time, start_t: dt_time, end_t: dt_time) -> bool:
        """Check if now_t is within [start_t, end_t). Supports overnight (e.g. 19:00→07:00)."""
        if start_t <= end_t:
            return start_t <= now_t < end_t
        else:
            return now_t >= start_t or now_t < end_t

    def _load_scheduler_config(self) -> Dict[str, Any]:
        """Read scheduler settings from profile config (nested) or legacy config (flat)."""
        try:
            raw = self._config_path.read_text(encoding="utf-8")
            cfg = json.loads(raw)
        except Exception:
            cfg = {}
        # Support nested profile format
        sched = cfg.get("scheduler", {})
        if sched:
            return {
                "enabled": sched.get("enabled", False),
                "regular_from": dt_time(*map(int, (sched.get("regular_from") or "07:00").split(":"))),
                "regular_to": dt_time(*map(int, (sched.get("regular_to") or "19:00").split(":"))),
                "heavy_from": dt_time(*map(int, (sched.get("heavy_from") or "19:00").split(":"))),
                "heavy_to": dt_time(*map(int, (sched.get("heavy_to") or "07:00").split(":"))),
                "interval": max(int(sched.get("interval_minutes", 10)), 1),
                "report_folder": sched.get("report_folder", ""),
            }
        # Legacy flat format
        return {
            "enabled": cfg.get("scheduler_enabled", False),
            "regular_from": dt_time(*map(int, cfg.get("scheduler_regular_from", "07:00").split(":"))),
            "regular_to": dt_time(*map(int, cfg.get("scheduler_regular_to", "19:00").split(":"))),
            "heavy_from": dt_time(*map(int, cfg.get("scheduler_heavy_from", "19:00").split(":"))),
            "heavy_to": dt_time(*map(int, cfg.get("scheduler_heavy_to", "07:00").split(":"))),
            "interval": max(int(cfg.get("scheduler_interval_minutes", 10)), 1),
            "report_folder": cfg.get("scheduler_report_folder", ""),
        }

    def start_scheduler(self) -> None:
        """Start the background scheduler thread."""
        with self._lock:
            if self._scheduler_thread and self._scheduler_thread.is_alive():
                return
            self._scheduler_stop.clear()
            self.scheduler_active = True
            self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self._scheduler_thread.start()
        self._on_status("🕐 תזמון אוטומטי הופעל")

    def stop_scheduler(self) -> None:
        """Stop the background scheduler thread."""
        self._scheduler_stop.set()
        self.scheduler_active = False
        self._on_status("🕐 תזמון אוטומטי נעצר")

    def _scheduler_loop(self) -> None:
        """Background loop: check time, run appropriate type, sleep interval."""
        import logging
        _sched_logger = logging.getLogger("automation_runner")
        while not self._scheduler_stop.is_set():
            try:
                sched = self._load_scheduler_config()
                if not sched["enabled"]:
                    self._on_status("🕐 תזמון כבוי — עוצר scheduler")
                    break

                now_t = datetime.now().time()
                run_type = None
                if self._time_in_range(now_t, sched["regular_from"], sched["regular_to"]):
                    run_type = "regular"
                elif self._time_in_range(now_t, sched["heavy_from"], sched["heavy_to"]):
                    run_type = "heavy"

                if run_type and not self.is_busy and not self.is_running:
                    if run_type == "regular":
                        self._on_status(f"🕐 תזמון: מריץ סבב רגיל ({now_t.strftime('%H:%M')})")
                        self._run_scheduled("regular")
                    else:
                        self._on_status(f"🕐 תזמון: מריץ כבדים ({now_t.strftime('%H:%M')})")
                        self._run_scheduled("heavy")
                elif run_type is None:
                    self._on_status(f"🕐 תזמון: לא בטווח שעות ({now_t.strftime('%H:%M')}), ממתין...")

                # Calculate sleep duration — if in a gap between windows,
                # sleep only until the next window starts instead of the full interval.
                sleep_seconds = sched["interval"] * 60
                self._next_run_time = datetime.now() + timedelta(seconds=sleep_seconds)
                next_t = self._next_run_time.strftime("%H:%M:%S")
                self._on_status(f"הסבב הושלם | הסבב הבא: {next_t}")
                if run_type is None:
                    # Find seconds until the nearest upcoming window
                    now_dt = datetime.now()
                    today = now_dt.date()
                    tomorrow = today + timedelta(days=1)
                    candidates = [
                        datetime.combine(today, sched["regular_from"]),
                        datetime.combine(today, sched["heavy_from"]),
                        datetime.combine(tomorrow, sched["regular_from"]),
                        datetime.combine(tomorrow, sched["heavy_from"]),
                    ]
                    future = [c for c in candidates if c > now_dt]
                    if future:
                        secs_to_next = (min(future) - now_dt).total_seconds()
                        # Add 1 second buffer to land just inside the window
                        sleep_seconds = min(sleep_seconds, int(secs_to_next) + 1)
                        sleep_seconds = max(sleep_seconds, 1)

                for _ in range(sleep_seconds):
                    if self._scheduler_stop.is_set():
                        break
                    time.sleep(1)

            except Exception as exc:
                _sched_logger.error(f"🕐 Scheduler loop error: {exc}", exc_info=True)
                self._on_status(f"🕐 תזמון: שגיאה בלולאה — {exc}, ממשיך בעוד 30 שניות...")
                # Sleep 30 seconds and retry instead of dying
                for _ in range(30):
                    if self._scheduler_stop.is_set():
                        break
                    time.sleep(1)

        self.scheduler_active = False

    def _run_scheduled(self, run_type: str) -> None:
        """Execute a scheduled run synchronously (called from scheduler thread)."""
        if not self._run_lock.acquire(blocking=False):
            self._on_status("🕐 תזמון: ריצה כבר פעילה — מדלג על סבב")
            return
        self._next_run_time = None
        self.is_busy = True
        self._busy_run_type = run_type
        run_start = datetime.now()
        try:
            if run_type == "heavy":
                self._runner.run_heavy()
            else:
                self._runner.run_once()
        except Exception as e:
            self._on_status(f"🕐 תזמון: שגיאה — {e}")
        finally:
            self._last_run_type = run_type
            self.is_busy = False
            self._busy_run_type = ""
            self._run_lock.release()

        # ── Export Excel report after run ──────────────────────
        try:
            cfg = self._load_scheduler_config()
            report_folder = cfg.get("report_folder", "")
            if report_folder:
                from streamlit_app.backend.report_exporter import export_schedule_report
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                saved_path = export_schedule_report(report_folder, run_type, today_start)
                self._on_status(f"📊 דוח נשמר: {saved_path}")
        except Exception as exc:
            self._on_status(f"📊 שגיאה בשמירת דוח Excel: {exc}")

    def get_log_lines(self, last_n: int = 100) -> list[str]:
        with self._lock:
            return self._log_lines[-last_n:]

    def clear_log(self) -> None:
        with self._lock:
            self._log_lines.clear()

    def get_run_status(self) -> Dict[str, Any]:
        """Parse recent log lines for progress info.
        Returns dict with: current_email, total_emails, last_status, next_run, phase, run_type."""
        with self._lock:
            lines = list(self._log_lines[-200:])

        # If in-memory lines are sparse, supplement with per-profile status_log.txt
        if len(lines) < 5:
            try:
                _sl = self._state_path.parent / "status_log.txt"
                if _sl.exists():
                    _raw = _sl.read_text(encoding="utf-8", errors="replace").splitlines()
                    file_lines = [l.strip() for l in _raw[-200:] if l.strip()]
                    # Merge: file_lines first, then in-memory (which may be newer)
                    seen = set(lines)
                    for fl in file_lines:
                        if fl not in seen:
                            lines.append(fl)
                            seen.add(fl)
            except Exception:
                pass

        status: Dict[str, Any] = {
            "current_email": 0,
            "total_emails": 0,
            "last_status": "",
            "next_run": "",
            "phase": "idle",  # idle, scanning, processing, sending, done, waiting
            "run_type": "",   # "" | "regular" | "heavy"
        }

        if not lines:
            return status

        # Walk backwards — first match wins for each field.
        # Once an active phase is found, older lines can't downgrade it.
        _phase_set = False

        for line in reversed(lines):
            # "הסבב הושלם | הסבב הבא: 20:50:20"
            if "הסבב הבא" in line and not status["next_run"]:
                m = re.search(r"הסבב הבא:\s*(\d{1,2}:\d{2}:\d{2})", line)
                if m:
                    status["next_run"] = m.group(1)
                if not _phase_set:
                    if "הושלם" in line:
                        status["phase"] = "done"
                    elif "אין מיילים" in line:
                        status["phase"] = "done"
                    _phase_set = True

            # Detect heavy mode
            if "כבדים" in line or "HEAVY" in line or "🏋️" in line:
                if not status["run_type"]:
                    status["run_type"] = "heavy"

            # "מוריד מייל 3/5 | mailbox: ..."
            if "מוריד מייל" in line and status["current_email"] == 0:
                m = re.search(r"מוריד מייל (\d+)/(\d+)", line)
                if m:
                    status["current_email"] = int(m.group(1))
                    status["total_emails"] = int(m.group(2))
                    if not _phase_set:
                        status["phase"] = "processing"
                        _phase_set = True
                    if not status["run_type"]:
                        status["run_type"] = "regular"

            # "מריץ ניתוח [3/5]"
            if "מריץ ניתוח" in line and status["current_email"] == 0:
                m = re.search(r"\[(\d+)/(\d+)\]", line)
                if m:
                    status["current_email"] = int(m.group(1))
                    status["total_emails"] = int(m.group(2))
                    if not _phase_set:
                        status["phase"] = "processing"
                        _phase_set = True
                    if not status["run_type"]:
                        status["run_type"] = "regular"

            # "⚡ Stage 1 (Basic Info) | model=..." — stage execution
            if "Stage " in line and not _phase_set:
                if re.search(r'Stage \d', line):
                    status["phase"] = "processing"
                    _phase_set = True

            # Drawing pipeline processing indicators
            if not _phase_set and any(k in line for k in (
                "Estimated dimensions", "Extracting high-res",
                "pdfplumber", "Azure Vision", "Creating overview",
            )):
                status["phase"] = "processing"
                _phase_set = True

            # "שולח מייל..."
            if "שולח מייל" in line and not _phase_set:
                status["phase"] = "sending"
                _phase_set = True

            # "בודק שוב ללא סינון תאריך" / "בודק מיילים חדשים"
            if "בודק" in line and not _phase_set:
                status["phase"] = "scanning"
                _phase_set = True

        # If actively processing, next_run from previous cycle is stale — clear it
        if status["phase"] in ("processing", "scanning", "sending"):
            status["next_run"] = ""

        # Override with direct tracking from is_busy (authoritative source)
        if self.is_busy:
            if self._busy_run_type:
                status["run_type"] = self._busy_run_type
            if status["phase"] == "idle":
                status["phase"] = "scanning"

        status["last_status"] = lines[-1] if lines else ""

        # Persist last run info for display between cycles
        if status["run_type"]:
            self._last_run_type = status["run_type"]
        if status["total_emails"]:
            self._last_email_count = status["total_emails"]
        # Carry forward last run type if current is empty
        if not status["run_type"] and self._last_run_type:
            status["run_type"] = self._last_run_type
        if not status["total_emails"] and self._last_email_count:
            status["total_emails"] = self._last_email_count

        return status


# ═══════════════════════════════════════════════════════════════════
# PipelineBridge — Multi-profile DocumentPipeline manager
# ═══════════════════════════════════════════════════════════════════

_pipeline_bridge_lock = threading.Lock()
_pipeline_bridge_instance: Optional["PipelineBridge"] = None


def get_pipeline_bridge() -> "PipelineBridge":
    """Return the process-level PipelineBridge singleton."""
    global _pipeline_bridge_instance
    with _pipeline_bridge_lock:
        if _pipeline_bridge_instance is None:
            _pipeline_bridge_instance = PipelineBridge()
        return _pipeline_bridge_instance


class PipelineBridge:
    """Manages all profiles through RunnerBridge instances.

    Each profile gets its own RunnerBridge → AutomationRunner with
    its own config, state, scheduler, and processing thread.
    All profiles use the same proven automation pipeline.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    # ── Core operations (delegate to per-profile RunnerBridge) ────

    def run_once(self, profile_name: str) -> bool:
        """Run a single cycle for the given profile."""
        bridge = get_runner_bridge(profile_name)
        return bridge.run_once()

    def run_heavy(self, profile_name: str) -> bool:
        """Run heavy processing for the given profile."""
        bridge = get_runner_bridge(profile_name)
        return bridge.run_heavy()

    def start(self, profile_name: str) -> bool:
        """Start continuous loop for the given profile."""
        bridge = get_runner_bridge(profile_name)
        return bridge.start()

    def stop(self, profile_name: str) -> None:
        """Stop the given profile (loop + scheduler)."""
        bridge = get_runner_bridge(profile_name)
        bridge.stop()

    def is_running(self, profile_name: str) -> bool:
        """Check if the given profile is running."""
        bridge = get_runner_bridge(profile_name)
        return bridge.is_running or bridge.is_busy

    # ── Per-profile scheduler ─────────────────────────────────────

    def is_scheduler_active(self, profile_name: str) -> bool:
        bridge = get_runner_bridge(profile_name)
        return bridge.scheduler_active

    def start_scheduler(self, profile_name: str) -> None:
        """Start the scheduler thread for a specific profile."""
        bridge = get_runner_bridge(profile_name)
        bridge.start_scheduler()

    def stop_scheduler(self, profile_name: str) -> None:
        """Stop the scheduler thread for a specific profile."""
        bridge = get_runner_bridge(profile_name)
        bridge.stop_scheduler()

    # ── Status + logs ─────────────────────────────────────────────

    def get_log_lines(self, profile_name: str, last_n: int = 100) -> list:
        """Get recent log lines for a profile."""
        bridge = get_runner_bridge(profile_name)
        return bridge.get_log_lines(last_n)

    def get_next_run_time(self, profile_name: str) -> Optional[datetime]:
        """Return the datetime of the next scheduled run, or None."""
        bridge = get_runner_bridge(profile_name)
        return bridge._next_run_time

    def get_run_status(self, profile_name: str) -> Dict[str, Any]:
        """Get run status for a profile."""
        bridge = get_runner_bridge(profile_name)
        return bridge.get_run_status()

    def get_all_status(self) -> Dict[str, Dict]:
        """Get status for all loaded profiles."""
        from streamlit_app.backend.config_manager import load_all_profiles
        statuses = {}
        for profile in load_all_profiles():
            name = profile["profile_name"]
            statuses[name] = {
                "display_name": profile.get("display_name", name),
                "running": self.is_running(name),
                "scheduler": self.is_scheduler_active(name),
                "engine_type": profile.get("ai_engine", {}).get("type", "?"),
            }
        return statuses
