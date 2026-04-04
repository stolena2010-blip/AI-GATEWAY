"""
Log Reader — Read and filter automation JSONL logs + live log files
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

LOG_DIR = Path(__file__).resolve().parent.parent.parent
JSONL_PATH = LOG_DIR / "automation_log.jsonl"
LOGS_FOLDER = LOG_DIR / "logs"


def _read_jsonl_file(path: Path) -> List[Dict[str, Any]]:
    """Read all valid JSON entries from a single JSONL file."""
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return entries


def load_log_entries(max_entries: int = 10000, profile_name: str = "quotes") -> List[Dict[str, Any]]:
    """Load entries from ALL automation_log*.jsonl files for a profile, deduplicated by id."""
    seen_ids: set = set()
    all_entries: List[Dict[str, Any]] = []

    # Per-profile log directory
    profile_dir = LOG_DIR / "data" / profile_name

    # Gather log files: per-profile dir first, then legacy root (for migration)
    log_files: List[Path] = []
    if profile_dir.exists():
        log_files.extend(profile_dir.glob("automation_log*.jsonl"))
        bak = profile_dir / "automation_log.jsonl.bak"
        if bak.exists() and bak not in log_files:
            log_files.append(bak)
    # Legacy root files — only for "quotes" (all legacy data is quotes)
    if not log_files and profile_name == "quotes":
        log_files = list(LOG_DIR.glob("automation_log*.jsonl"))
        bak = LOG_DIR / "automation_log.jsonl.bak"
        if bak.exists() and bak not in log_files:
            log_files.append(bak)

    for path in log_files:
        for entry in _read_jsonl_file(path):
            eid = entry.get("id", "")
            if eid and eid in seen_ids:
                continue
            if eid:
                seen_ids.add(eid)
            all_entries.append(entry)

    # Sort by timestamp ascending, then reverse for most-recent-first
    def _ts(e):
        ts = e.get("timestamp") or e.get("start_time") or ""
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            return datetime.min

    all_entries.sort(key=_ts, reverse=True)
    return all_entries[:max_entries]


def filter_by_period(entries: List[Dict[str, Any]], period: str,
                     date_from: str = "", date_to: str = "") -> List[Dict[str, Any]]:
    """Filter entries by period: today, week, month, all, or custom range."""
    if period == "הכל" and not date_from and not date_to:
        return entries
    if not entries:
        return entries

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff_start = None
    cutoff_end = None

    if period == "היום":
        cutoff_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "שבוע":
        cutoff_start = now - timedelta(days=7)
    elif period == "חודש":
        cutoff_start = now - timedelta(days=30)
    elif period == "טווח" and date_from:
        try:
            cutoff_start = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            pass
        if date_to:
            try:
                cutoff_end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            except ValueError:
                pass

    if cutoff_start is None and cutoff_end is None:
        return entries

    filtered = []
    for e in entries:
        ts = e.get("timestamp") or e.get("start_time") or ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            if cutoff_start and dt < cutoff_start:
                continue
            if cutoff_end and dt >= cutoff_end:
                continue
            filtered.append(e)
        except (ValueError, AttributeError):
            filtered.append(e)
    return filtered


def get_accuracy_weights() -> Dict[str, float]:
    """Load accuracy weights from environment (same as original dashboard)."""
    return {
        "full":   float(os.getenv("ACCURACY_WEIGHT_FULL", "1.0")),
        "high":   float(os.getenv("ACCURACY_WEIGHT_HIGH", "1.0")),
        "medium": float(os.getenv("ACCURACY_WEIGHT_MEDIUM", "0.8")),
        "low":    float(os.getenv("ACCURACY_WEIGHT_LOW", "0.5")),
        "none":   float(os.getenv("ACCURACY_WEIGHT_NONE", "0.0")),
    }


def calc_weighted_accuracy(accuracy_data: Dict[str, Any], weights: Dict[str, float]) -> float:
    """Calculate weighted accuracy % for one entry. Returns 0-100."""
    total = int(accuracy_data.get("total", 0) or 0)
    if total == 0:
        return 0.0
    score = sum(
        int(accuracy_data.get(level, 0) or 0) * weights.get(level, 0)
        for level in ("full", "high", "medium", "low", "none")
    )
    return (score / total) * 100


def save_entry_field(entry_id: str, field: str, value: Any, profile_name: str = "quotes") -> bool:
    """Update a single field on a log entry in-place.
    Rewrites the JSONL file with the updated entry. Returns True on success."""
    profile_jsonl = LOG_DIR / "data" / profile_name / "automation_log.jsonl"
    target = profile_jsonl if profile_jsonl.exists() else JSONL_PATH
    if not target.exists():
        return False
    lines = target.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            new_lines.append(line)
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue
        if entry.get("id") == entry_id:
            entry[field] = value
            new_lines.append(json.dumps(entry, ensure_ascii=False))
            updated = True
        else:
            new_lines.append(line)
    if updated:
        target.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return updated


def get_latest_log_file() -> Optional[Path]:
    """Find the most recent log file in logs/ directory."""
    if not LOGS_FOLDER.exists():
        return None
    # Today's log first, then most recent
    today_str = datetime.now().strftime("%Y%m%d")
    today_log = LOGS_FOLDER / f"drawingai_{today_str}.log"
    if today_log.exists():
        return today_log
    log_files = sorted(LOGS_FOLDER.glob("drawingai_*.log"), reverse=True)
    return log_files[0] if log_files else None


STATUS_LOG = LOG_DIR / "status_log.txt"

import re as _re
_ANSI_RE = _re.compile(r'\x1b\[[0-9;]*m')


def _parse_log_file_line(line: str) -> str:
    """Convert a drawingai_*.log line to the same format as the console
    (HH:MM:SS │ module │ LEVEL │ message), stripping the date prefix."""
    line = _ANSI_RE.sub('', line)
    parts = line.split(" │ ")
    if len(parts) >= 4:
        timestamp = parts[0].strip()
        # Strip date prefix, keep only HH:MM:SS
        time_short = timestamp.split(" ")[-1] if " " in timestamp else timestamp
        return f"{time_short} │ " + " │ ".join(p.strip() for p in parts[1:])
    return line


def _extract_timestamp(line: str) -> str:
    """Extract HH:MM:SS timestamp from either [HH:MM:SS] or HH:MM:SS │ ... format."""
    line = line.strip()
    if line.startswith("[") and "]" in line:
        return line[1:line.index("]")]
    # Logger format: HH:MM:SS │ ...
    if " │ " in line and len(line) >= 8:
        candidate = line[:8]
        if len(candidate) == 8 and candidate[2] == ':' and candidate[5] == ':':
            return candidate
    return "99:99:99"


def _get_profile_status_log(profile_name: str = "quotes") -> Path:
    """Return the per-profile status_log.txt path."""
    return LOG_DIR / "data" / profile_name / "status_log.txt"


def read_log_tail(n_lines: int = 100, profile_name: str = "quotes") -> str:
    """Read per-profile status_log.txt which contains both print() output and
    logger output, providing the same detail level as the terminal."""
    lines: list[str] = []

    profile_log = _get_profile_status_log(profile_name)

    # ── Primary source: per-profile status_log.txt ──
    if profile_log.exists():
        try:
            raw = profile_log.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in raw:
                clean = _ANSI_RE.sub('', line).strip()
                if clean:
                    lines.append(clean)
        except Exception:
            pass

    # ── Fallback: legacy root status_log.txt (migration period) ──
    if not lines and STATUS_LOG.exists():
        try:
            raw = STATUS_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in raw:
                clean = _ANSI_RE.sub('', line).strip()
                if clean:
                    lines.append(clean)
        except Exception:
            pass

    # ── Fallback: drawingai_*.log (if status_log is empty, e.g. first run) ──
    if not lines:
        log_file = get_latest_log_file()
        if log_file:
            try:
                raw = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
                for line in raw:
                    if line.strip():
                        lines.append(_parse_log_file_line(line))
            except Exception:
                pass

    if not lines:
        return "(אין קבצי לוג)"

    # ── Sort by timestamp ──
    lines.sort(key=_extract_timestamp)

    # ── Deduplicate exact lines ──
    seen: set = set()
    deduped: list[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            deduped.append(line)

    tail = deduped[-n_lines:]
    return "\n".join(tail)


def detect_active_run(profile_name: str = "quotes") -> dict:
    """Detect active run from per-profile status_log.txt timestamps and keywords.
    Returns dict with active (bool), run_type ('heavy'|'regular'|''), email_progress ('3/5'|'').
    Works even when session_state.runner is None (e.g. after browser refresh)."""
    import re
    result = {"active": False, "run_type": "", "email_progress": ""}
    _log = _get_profile_status_log(profile_name)
    # Fallback to legacy root log during migration
    if not _log.exists():
        _log = STATUS_LOG
    if not _log.exists():
        return result
    try:
        mtime = _log.stat().st_mtime
        age = datetime.now().timestamp() - mtime
        if age > 120:  # File not modified in last 2 minutes
            return result

        raw = STATUS_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = [l.strip() for l in raw[-60:] if l.strip()]
        if not tail:
            return result

        # Check latest timestamp — is it recent?
        now = datetime.now()
        latest_ts = None
        for line in reversed(tail):
            m = re.search(r'(\d{1,2}:\d{2}:\d{2})', line)
            if m:
                try:
                    t = datetime.strptime(m.group(1), "%H:%M:%S").replace(
                        year=now.year, month=now.month, day=now.day)
                    if abs((now - t).total_seconds()) < 120:
                        latest_ts = t
                    break
                except ValueError:
                    pass

        if latest_ts is None:
            return result

        # Recent activity detected — check keywords
        combined = "\n".join(tail[-40:])
        is_heavy = any(k in combined for k in ("כבדים", "HEAVY", "🏋️"))
        is_processing = any(k in combined for k in (
            "מוריד מייל", "מריץ ניתוח", "Stage ",
            "Estimated dimensions", "Extracting high-res",
            "pdfplumber", "Azure Vision",
        ))
        # Check last 3 lines for definitive completion markers
        # Only "הסבב הושלם" or "אין מיילים חדשים בכל התיבות" are real end markers
        # NOTE: "אין מיילים כבדים" per-mailbox is NOT done!
        is_done = False
        for check_line in tail[-3:]:
            if "הסבב הושלם" in check_line:
                is_done = True
                break
            if "אין מיילים חדשים בכל" in check_line:
                is_done = True
                break
            if "הסבב הבא" in check_line:
                is_done = True
                break

        if is_processing and not is_done:
            result["active"] = True
            result["run_type"] = "heavy" if is_heavy else "regular"
            # Try to extract email progress
            for rl in reversed(tail[-30:]):
                pm = re.search(r'מוריד מייל (\d+)/(\d+)', rl)
                if not pm:
                    pm = re.search(r'מריץ ניתוח \[(\d+)/(\d+)\]', rl)
                if pm:
                    result["email_progress"] = f"{pm.group(1)}/{pm.group(2)}"
                    break
    except Exception:
        pass
    return result


def get_countdown(profile_name: str = "quotes") -> dict:
    """Calculate countdown to next automation run from state + config files.
    Returns dict with next_run (str), remaining_seconds (int), remaining_text (str)."""
    import json
    profile_state = LOG_DIR / "data" / profile_name / "state.json"
    config_path = LOG_DIR / "automation_config.json"
    result = {"next_run": "", "remaining_seconds": -1, "remaining_text": ""}
    try:
        state = json.loads(profile_state.read_text(encoding="utf-8"))
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return result

    last_checked = state.get("last_checked", "")
    interval = max(int(config.get("poll_interval_minutes", 10)), 1)

    if not last_checked:
        return result

    try:
        # Parse ISO timestamp (may have Z or +00:00)
        lc = last_checked.replace("Z", "+00:00")
        last_dt = datetime.fromisoformat(lc).replace(tzinfo=None)
    except (ValueError, TypeError):
        return result

    from datetime import timedelta
    next_dt = last_dt + timedelta(minutes=interval)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    remaining = (next_dt - now).total_seconds()

    if remaining < 0:
        result["remaining_text"] = "ממתין לריצה..."
        result["remaining_seconds"] = 0
    else:
        mins = int(remaining) // 60
        secs = int(remaining) % 60
        result["remaining_text"] = f"{mins}:{secs:02d}"
        result["remaining_seconds"] = int(remaining)

    result["next_run"] = next_dt.strftime("%H:%M:%S")
    return result


# ═══════════════════════════════════════════════════════════════════
# Multi-profile log loading
# ═══════════════════════════════════════════════════════════════════

def load_profile_log_entries(profile_name: str, max_entries: int = 5000) -> List[Dict[str, Any]]:
    """Load log entries for a specific profile from its JSONL log file."""
    log_path = LOG_DIR / "logs" / f"{profile_name}_log.jsonl"
    if not log_path.exists():
        return []
    entries = _read_jsonl_file(log_path)
    # Also check project root (legacy location)
    alt_path = LOG_DIR / f"{profile_name}_log.jsonl"
    if alt_path.exists():
        entries.extend(_read_jsonl_file(alt_path))

    def _ts(e):
        ts = e.get("timestamp") or e.get("start_time") or ""
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            return datetime.min

    entries.sort(key=_ts, reverse=True)
    return entries[:max_entries]


def load_all_profile_log_entries(
    profile_names: Optional[List[str]] = None,
    max_entries: int = 10000,
) -> List[Dict[str, Any]]:
    """Load log entries from multiple profiles, merged and sorted.

    If profile_names is None, loads from all profiles + legacy log.
    """
    all_entries = []

    # Load log entries per requested profile (or legacy/quotes as fallback)
    if profile_names:
        for pname in profile_names:
            all_entries.extend(load_log_entries(max_entries, profile_name=pname))
    else:
        all_entries.extend(load_log_entries(max_entries))

    # Per-profile logs (from logs/{profile}_log.jsonl)
    if profile_names is None:
        # Auto-discover from logs/ directory
        logs_dir = LOG_DIR / "logs"
        if logs_dir.exists():
            for f in logs_dir.glob("*_log.jsonl"):
                pname = f.stem.replace("_log", "")
                all_entries.extend(load_profile_log_entries(pname, max_entries))
    else:
        for pname in profile_names:
            all_entries.extend(load_profile_log_entries(pname, max_entries))

    # Deduplicate by id
    seen = set()
    deduped = []
    for e in all_entries:
        eid = e.get("id", "")
        if eid and eid in seen:
            continue
        if eid:
            seen.add(eid)
        deduped.append(e)

    def _ts(e):
        ts = e.get("timestamp") or e.get("start_time") or ""
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            return datetime.min

    deduped.sort(key=_ts, reverse=True)
    return deduped[:max_entries]
