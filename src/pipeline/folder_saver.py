"""
folder_saver — Save per-folder output files (Excel, classification, B2B text, rename).
Extracted from customer_extractor_v3_dual.scan_folder() save block.
"""
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.services.file.file_utils import _build_drawing_part_map
from src.utils.logger import get_logger

logger = get_logger(__name__)


def save_folder_output(
    target_folder: Path,
    subfolder_results: List[Dict[str, Any]],
    file_classifications: List[Dict[str, Any]],
    pl_items_list: List[Dict[str, Any]],
    confidence_level: str,
    timestamp: str,
    *,
    folder_classification_cost: float = 0.0,
    folder_extraction_cost_accurate: float = 0.0,
    folder_extraction_tokens_in: int = 0,
    folder_extraction_tokens_out: int = 0,
    folder_stage6_tokens_in: int = 0,
    folder_stage6_tokens_out: int = 0,
    folder_start_time: float = 0.0,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Save all per-folder output artefacts.

    Returns:
        (folder_info_dict_or_None, enriched_subfolder_results)
    """
    from src.services.ai import ModelRuntimeConfig as _MRC
    from src.services.ai.vision_api import _calculate_stage_cost
    from src.services.file.file_renamer import rename_files_by_classification as _rename_files_by_classification
    from src.services.reporting.excel_export import (
        _save_classification_report,
        _save_results_to_excel,
        _update_pl_sheet_with_associated_items,
    )
    from src.services.reporting.b2b_export import _save_text_summary_with_variants
    _rt = _MRC.from_env()
    MODEL_INPUT_PRICE_PER_1M = _rt.input_price_per_1m
    MODEL_OUTPUT_PRICE_PER_1M = _rt.output_price_per_1m
    STAGE_PL = 6

    safe_folder_name = _safe_name(target_folder)

    # ── 1. Drawing results Excel ──
    if subfolder_results:
        logger.info(f"Saving files in folder '{target_folder.name}'...")
        results_file = target_folder / f"drawing_results_{safe_folder_name}.xlsx"
        _save_results_to_excel(subfolder_results, results_file, pl_items_list)
        logger.info(f"✓ Drawing analysis: {results_file.name} ({len(subfolder_results)} drawings)")
    else:
        results_file = None

    # ── 2. Classification Excel ──
    if file_classifications:
        # Backfill item_number/revision for drawings from actual results
        if subfolder_results:
            drawing_index = {
                dr.get('file_name'): dr for dr in subfolder_results if dr.get('file_name')
            }
            for fc in file_classifications:
                if 'original_filename' not in fc:
                    fc['original_filename'] = fc['file_path'].name
                if fc.get('file_type') == 'DRAWING':
                    dr = drawing_index.get(fc['file_path'].name)
                    if dr:
                        fc['item_number'] = dr.get('drawing_number', '')
                        fc['revision'] = dr.get('revision', '')

        safe_fn2 = _safe_name(target_folder)
        classification_file = target_folder / f"file_classification_{safe_fn2}.xlsx"
        drawing_map = _build_drawing_part_map(file_classifications, subfolder_results)
        _save_classification_report(
            file_classifications, target_folder, 0, 0,
            custom_filename=classification_file.name,
            drawing_map=drawing_map,
            drawing_results=subfolder_results,
        )
        logger.info(f"✓ File mapping: {classification_file.name} ({len(file_classifications)} files)")

        # Update PL sheet with associated_items
        if subfolder_results and results_file:
            if classification_file.exists() and results_file.exists():
                logger.info("Updating Parts_List_Items with associated_items...")
                _update_pl_sheet_with_associated_items(results_file, classification_file)
    else:
        classification_file = None

    # ── 3. B2B text file + email enrichment ──
    if subfolder_results:
        sender_email, subject_text = _read_email_header(target_folder)

        for result_dict in subfolder_results:
            if not result_dict.get('email_from'):
                result_dict['email_from'] = sender_email
                result_dict['email_subject'] = subject_text

        quote_or_order_number = _resolve_request_id(
            file_classifications, subject_text, target_folder, timestamp,
        )

        b2b_number = "B2B-0_200002"
        text_filename = f"{b2b_number}-{quote_or_order_number}.txt"
        text_path = target_folder / text_filename
        _save_text_summary_with_variants(subfolder_results, text_path, sender_email, b2b_number, quote_or_order_number)

    # ── 4. Rename files by classification ──
    if file_classifications:
        renamed_count = _rename_files_by_classification(file_classifications)
        if renamed_count > 0:
            logger.info(f"Total renamed: {renamed_count} files")

    # ── 5. Folder statistics ──
    folder_info = _build_folder_stats(
        target_folder, file_classifications, subfolder_results,
        folder_classification_cost=folder_classification_cost,
        folder_extraction_cost_accurate=folder_extraction_cost_accurate,
        folder_extraction_tokens_in=folder_extraction_tokens_in,
        folder_extraction_tokens_out=folder_extraction_tokens_out,
        folder_stage6_tokens_in=folder_stage6_tokens_in,
        folder_stage6_tokens_out=folder_stage6_tokens_out,
        folder_start_time=folder_start_time,
    )

    return folder_info, subfolder_results


# ===== internal helpers =====================================================

def _safe_name(target_folder: Path) -> str:
    safe = target_folder.name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    max_filename = len("file_classification_") + len(safe) + len(".xlsx")
    max_full = len(str(target_folder)) + 1 + max_filename
    if max_full > 250:
        over = max_full - 250
        safe = safe[:len(safe) - over]
        logger.info(f"📏 Truncated safe_folder_name to {len(safe)} chars (path was {max_full} > 250)")
    return safe


def _read_email_header(target_folder: Path) -> Tuple[str, str]:
    sender_email = ""
    subject_text = ""
    email_file = target_folder / "email.txt"
    if not email_file.exists():
        return sender_email, subject_text
    try:
        with open(email_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        if lines:
            first_line = lines[0].strip()
            if first_line and "@" in first_line:
                sender_email = first_line.replace("כתובת שולח:", "").replace("From:", "").strip()
        for line in lines:
            ls = line.strip()
            if ls.lower().startswith("from:") and "@" in ls and not sender_email:
                sender_email = ls.split(":", 1)[1].strip()
                continue
            if ls.lower().startswith("subject:"):
                subject_text = ls.split(":", 1)[1].strip()
                break
            if ls.startswith("נושא:"):
                subject_text = ls.split(":", 1)[1].strip()
                break
    except Exception:
        pass
    return sender_email, subject_text


def _resolve_request_id(
    file_classifications: Optional[List[Dict]],
    subject_text: str,
    target_folder: Path,
    timestamp: str,
) -> str:
    """Determine quote/order number for B2B filename."""
    quote_or_order_number = ""
    if file_classifications and isinstance(file_classifications, list):
        for fc in file_classifications:
            if not fc or not isinstance(fc, dict):
                continue
            qn = str(fc.get('quote_number', '')).strip() if fc.get('quote_number') else ""
            on = str(fc.get('order_number', '')).strip() if fc.get('order_number') else ""
            if qn:
                return qn
            if on:
                return on

    def _extract_number(text: str) -> str:
        if not text:
            return ""
        patterns = [
            r'(?:quotation|quote|rfq|הצעת מחיר|הצעה)[^0-9]{0,12}(\d{4,12})',
            r'(?:order|po|הזמנת רכש|הזנת רכש)[^0-9]{0,12}(\d{4,12})',
            r'B2B[_\s-]*Quotation[_\s-]*(\d{4,12})',
            r'B2B[_\s-]*Order[_\s-]*(\d{4,12})',
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return m.group(1)
        m = re.search(r'(\d{5,12})', text)
        return m.group(1) if m else ""

    def _looks_like_date(value: str) -> bool:
        if not value or len(value) != 8 or not value.isdigit():
            return False
        try:
            parsed = datetime.strptime(value, "%Y%m%d")
            return 2000 <= parsed.year <= 2100
        except Exception:
            return False

    candidate = _extract_number(subject_text)
    if candidate and not _looks_like_date(candidate):
        return candidate
    candidate = _extract_number(target_folder.name)
    if candidate and not _looks_like_date(candidate):
        return candidate
    return timestamp


def _build_folder_stats(
    target_folder: Path,
    file_classifications: List[Dict[str, Any]],
    subfolder_results: List[Dict[str, Any]],
    *,
    folder_classification_cost: float,
    folder_extraction_cost_accurate: float,
    folder_extraction_tokens_in: int,
    folder_extraction_tokens_out: int,
    folder_stage6_tokens_in: int,
    folder_stage6_tokens_out: int,
    folder_start_time: float,
) -> Dict[str, Any]:
    from src.services.ai import ModelRuntimeConfig as _MRC
    from src.services.ai.vision_api import _calculate_stage_cost
    _rt = _MRC.from_env()
    MODEL_INPUT_PRICE_PER_1M = _rt.input_price_per_1m
    MODEL_OUTPUT_PRICE_PER_1M = _rt.output_price_per_1m
    STAGE_PL = 6

    file_type_counts = Counter(
        fc.get('file_type', 'UNKNOWN')
        for fc in (file_classifications or [])
        if fc and isinstance(fc, dict)
    )

    drawing_confidence_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    for result in (subfolder_results or []):
        conf = str(result.get('confidence_level', '')).strip().upper()
        if conf == 'FULL':
            conf = 'HIGH'
        if conf in drawing_confidence_counts:
            drawing_confidence_counts[conf] += 1

    if folder_extraction_cost_accurate > 0:
        folder_extraction_cost = folder_extraction_cost_accurate
    else:
        folder_extraction_cost = (
            (folder_extraction_tokens_in / 1_000_000) * MODEL_INPUT_PRICE_PER_1M
            + (folder_extraction_tokens_out / 1_000_000) * MODEL_OUTPUT_PRICE_PER_1M
        )

    folder_stage6_cost = _calculate_stage_cost(folder_stage6_tokens_in, folder_stage6_tokens_out, STAGE_PL)
    folder_total_time = time.time() - folder_start_time if folder_start_time else 0
    folder_total_cost = folder_classification_cost + folder_extraction_cost + folder_stage6_cost

    return {
        'name': target_folder.name,
        'total_files': len(file_classifications) if file_classifications else 0,
        'file_types': dict(file_type_counts),
        'total_drawings': len(subfolder_results) if subfolder_results else 0,
        'confidence_high': drawing_confidence_counts['HIGH'],
        'confidence_medium': drawing_confidence_counts['MEDIUM'],
        'confidence_low': drawing_confidence_counts['LOW'],
        'classification_cost': folder_classification_cost,
        'extraction_cost': folder_extraction_cost,
        'stage6_cost': folder_stage6_cost,
        'total_cost': folder_total_cost,
        'processing_time': folder_total_time,
    }
