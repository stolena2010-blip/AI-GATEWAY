"""
Process exclusion filter — removes unwanted processes from output fields.

Reads the exclusion list from ``לא עושים.xlsx`` (root of project).
Each row has columns: תהליך, סוג תהליך.

Applied to pipe-delimited fields:
  - merged_processes
  - merged_description
  - process_summary_hebrew
  - process_summary_hebrew_short
"""

import logging
from pathlib import Path
from typing import Dict, Set

import pandas as pd

logger = logging.getLogger(__name__)

_EXCLUDE_FILE = Path(__file__).resolve().parents[3] / "BOM" / "לא עושים.xlsx"

# Module-level cache — reloads automatically when the file changes
_excluded: Set[str] | None = None
_excluded_mtime: float = 0.0


def _load_excluded() -> Set[str]:
    """Load excluded process names from Excel (cached, auto-reloads on file change)."""
    global _excluded, _excluded_mtime

    if not _EXCLUDE_FILE.exists():
        logger.debug("No exclusion file found: %s", _EXCLUDE_FILE)
        _excluded = set()
        return _excluded

    # Reload if file was modified since last load
    current_mtime = _EXCLUDE_FILE.stat().st_mtime
    if _excluded is not None and current_mtime == _excluded_mtime:
        return _excluded

    try:
        df = pd.read_excel(_EXCLUDE_FILE)
        _excluded = set()
        for _, row in df.iterrows():
            name = str(row.get("תהליך", "")).strip()
            if name and name != "nan":
                _excluded.add(name)
        _excluded_mtime = current_mtime
        logger.info("Loaded %d excluded processes from '%s'", len(_excluded), _EXCLUDE_FILE.name)
    except Exception as e:
        logger.warning("Failed to load exclusion file: %s", e)
        _excluded = set()

    return _excluded


def _is_excluded(segment: str, excluded: Set[str]) -> bool:
    """Check if a pipe segment matches any excluded process (exact match)."""
    s = segment.strip()
    if s in excluded:
        return True
    return False


def _filter_pipe_field(value: str, excluded: Set[str]) -> str:
    """Remove excluded segments from a pipe-delimited field."""
    if not value or value == "nan":
        return value
    parts = [p.strip() for p in value.split("|")]
    filtered = [p for p in parts if not _is_excluded(p, excluded)]
    return " | ".join(filtered)


def filter_excluded_processes(result: Dict) -> Dict:
    """
    Remove excluded processes from all process description fields in a result dict.

    Modifies the dict in-place and returns it.
    """
    excluded = _load_excluded()
    if not excluded:
        return result

    # Filter pipe-delimited fields
    for field in ("merged_processes", "process_summary_hebrew", "process_summary_hebrew_short"):
        val = str(result.get(field) or "").strip()
        if val and val != "nan":
            result[field] = _filter_pipe_field(val, excluded)

    # Rebuild merged_description from filtered merged_processes
    # (It wraps merged_processes with "(תהליכים)" prefix and H.C suffix)
    desc = str(result.get("merged_description") or "").strip()
    if desc and desc != "nan" and "(תהליכים)" in desc:
        # Extract the process part between "(תהליכים) " and " | H.C=" (or end)
        import re
        m = re.match(r'^\(תהליכים\)\s*(.+?)(?:\s*\|\s*H\.C=(\d+))?$', desc)
        if m:
            procs_part = m.group(1)
            hc_part = m.group(2)
            filtered_procs = _filter_pipe_field(procs_part, excluded)
            if filtered_procs:
                if hc_part:
                    result["merged_description"] = f"(תהליכים) {filtered_procs} | H.C={hc_part}"
                else:
                    result["merged_description"] = f"(תהליכים) {filtered_procs}"
            else:
                # All processes were excluded — keep H.C if present
                result["merged_description"] = f"H.C={hc_part}" if hc_part else ""

    return result
