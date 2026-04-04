"""
pl_processor — Parts-list association, extraction, override, and propagation.
Extracted from customer_extractor_v3_dual.scan_folder() Phases 2c / 6 / 6b.
"""
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Phase 2c  —  Update associated_item for PL files in file_classifications
# ---------------------------------------------------------------------------

def update_pl_associations(
    subfolder_results: List[Dict[str, Any]],
    file_classifications: List[Dict[str, Any]],
) -> None:
    """Link PL files to their associated drawing via filename matching.

    Modifies *file_classifications* in-place (sets ``associated_item``).
    """
    from src.services.extraction.filename_utils import (
        _extract_item_number_from_filename,
        _normalize_item_number,
    )
    from src.services.file.file_utils import _find_associated_drawing

    if not subfolder_results or not file_classifications:
        if subfolder_results and not file_classifications:
            logger.error("file_classifications is None — skipping PL update")
        return

    pl_file_count = len([
        fc for fc in file_classifications
        if fc and isinstance(fc, dict) and fc.get('file_type') == 'PARTS_LIST'
    ])
    if pl_file_count == 0:
        logger.info("No PL files in file_classifications to update")
        return

    logger.info(f"Updating file_classifications with associated_item for {pl_file_count} PL files...")

    # Build drawing_map once
    temp_drawing_map: Dict[str, str] = {}
    for dr in subfolder_results:
        dr_file = dr.get('file_name', '')
        dr_part_num = dr.get('part_number', '')
        if dr_file and dr_part_num:
            temp_drawing_map[dr_file] = dr_part_num
            dr_item = _extract_item_number_from_filename(dr_file)
            if dr_item:
                temp_drawing_map[dr_item] = dr_part_num

    pl_files = [
        fc for fc in file_classifications
        if fc and isinstance(fc, dict)
        and fc.get('file_type') == 'PARTS_LIST'
        and not fc.get('associated_item')
    ]

    # Score all PLs against all drawings
    all_scores: List[Tuple[Dict, str, str]] = []
    for fc in pl_files:
        pl_filename = fc['file_path'].name if hasattr(fc.get('file_path'), 'name') else str(fc.get('file_path'))
        associated_part = _find_associated_drawing(fc['file_path'], 'PARTS_LIST', temp_drawing_map)
        if associated_part:
            all_scores.append((fc, associated_part, pl_filename))

    # Unique assignment — resolve conflicts when 2+ PLs match the same drawing
    by_pn: Dict[str, list] = defaultdict(list)
    for fc, pn, pl_name in all_scores:
        by_pn[pn].append((fc, pl_name))

    already_assigned: set = set()

    for pn, pl_list in by_pn.items():
        if len(pl_list) == 1:
            fc, pl_name = pl_list[0]
            fc['associated_item'] = pn
            already_assigned.add(pn)
            logger.info(f"PL: {pl_name} → associated_item: {pn}")
        else:
            logger.warning(f"⚠️ {len(pl_list)} PLs compete for {pn}: {[n for _, n in pl_list]}")
            best_fc, best_name, best_overlap = None, "", 0
            pn_clean = re.sub(r'[^a-z0-9]', '', pn.lower())

            for fc, pl_name in pl_list:
                pl_stem = fc['file_path'].stem.upper()
                pl_clean = re.sub(r'^PL[_\\-]?', '', pl_stem)
                pl_clean = re.sub(r'[_\\-][A-Z\\-]{1,3}$', '', pl_clean)
                pl_hint = re.sub(r'[^a-z0-9]', '', pl_clean.lower())
                overlap = 0
                for a, b in zip(pl_hint, pn_clean):
                    if a == b:
                        overlap += 1
                    else:
                        break
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_fc = fc
                    best_name = pl_name

            if best_fc:
                best_fc['associated_item'] = pn
                already_assigned.add(pn)
                logger.info(f"PL: {best_name} → associated_item: {pn} (won conflict)")

                for fc, pl_name in pl_list:
                    if fc.get('associated_item'):
                        continue
                    filtered_map = {
                        k: v for k, v in temp_drawing_map.items()
                        if (v if isinstance(v, str) else v.get('part_number', '')) not in already_assigned
                    }
                    alt = _find_associated_drawing(fc['file_path'], 'PARTS_LIST', filtered_map)
                    if alt:
                        fc['associated_item'] = alt
                        already_assigned.add(alt)
                        logger.info(f"PL: {pl_name} → associated_item: {alt} (second choice)")
                    else:
                        logger.warning(f"PL: {pl_name} → no unique match found")


# ---------------------------------------------------------------------------
# Phase 6  —  PL extraction, matching, override, and email override
# ---------------------------------------------------------------------------

def extract_and_process_pl(
    file_classifications: List[Dict[str, Any]],
    subfolder_results: List[Dict[str, Any]],
    client,
    email_data: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Run Stage 6: extract PL data, match to drawings, apply overrides.

    Returns:
        (pl_items_list, stage6_tokens_in, stage6_tokens_out)
    """
    from src.services.ai.vision_api import _calculate_stage_cost
    from src.services.extraction.quantity_matcher import (
        extract_base_and_suffix as _extract_base_and_suffix,
        override_pn_from_email as _override_pn_from_email,
    )
    from src.services.extraction.filename_utils import _normalize_item_number
    from src.services.reporting.pl_generator import extract_pl_data
    STAGE_PL = 6

    stage6_tokens_in = 0
    stage6_tokens_out = 0
    pl_items_list: List[Dict[str, Any]] = []

    pl_files = [
        fc for fc in (file_classifications or [])
        if fc and isinstance(fc, dict) and fc.get('file_type') == 'PARTS_LIST'
    ]

    if not pl_files:
        return pl_items_list, 0, 0

    logger.info(f"[STAGE6] Stage 6: Extract PL data ({len(pl_files)} parts lists)...")

    # --- extract PL data ---
    for pl_fc in pl_files:
        pl_path = pl_fc.get('file_path')
        if not pl_path:
            logger.error("PL file has no file_path!")
            continue
        logger.info(f"Processing: {pl_path.name if hasattr(pl_path, 'name') else pl_path}")
        try:
            pl_extracted, t_in, t_out = extract_pl_data(str(pl_path), client, file_classifications)
            if pl_extracted:
                pl_items_list.extend(pl_extracted)
                stage6_tokens_in += t_in
                stage6_tokens_out += t_out
                logger.info(f"Extracted {len(pl_extracted)} items from this PL (${_calculate_stage_cost(t_in, t_out, STAGE_PL):.4f})")
        except Exception as pl_error:
            logger.error(f"ERROR processing PL: {str(pl_error)[:100]}")

    # --- match PL items to drawings ---
    if subfolder_results and pl_items_list:
        _match_pl_items_to_drawings(pl_items_list, subfolder_results, _normalize_item_number)

    logger.info(f"Stage 6 complete: {len(pl_items_list)} PL items extracted")

    # --- propagate pl_main_part_number ---
    if subfolder_results and pl_items_list:
        _propagate_pl_main_pn(subfolder_results, pl_items_list, _normalize_item_number)

    # --- PL part-number override ---
    if subfolder_results and pl_items_list:
        _override_part_numbers(subfolder_results, pl_items_list,
                               _normalize_item_number, _extract_base_and_suffix)

        # --- email P.N. override ---
        _is_iai_email = any(
            'IAI' in str(r.get('customer_name', '')).upper()
            for r in subfolder_results if r.get('customer_name')
        )
        _override_pn_from_email(subfolder_results, email_data, is_iai=_is_iai_email)

    # --- update associated_item in file_classifications ---
    if subfolder_results and file_classifications:
        _update_assoc_after_override(subfolder_results, file_classifications, _normalize_item_number)

    return pl_items_list, stage6_tokens_in, stage6_tokens_out


# ---------------------------------------------------------------------------
# Phase 6b  —  Propagate PL Summary Hebrew + PL Hardware
# ---------------------------------------------------------------------------

def propagate_pl_data(
    subfolder_results: List[Dict[str, Any]],
    pl_items_list: List[Dict[str, Any]],
) -> None:
    """Copy PL Summary Hebrew and PL Hardware into matching drawing results."""
    from src.services.extraction.filename_utils import _normalize_item_number

    if not subfolder_results or not pl_items_list:
        return

    for result_dict in subfolder_results:
        part_num_norm = _normalize_item_number(result_dict.get('part_number', ''))
        ocr_orig_norm = _normalize_item_number(result_dict.get('part_number_ocr_original', ''))
        heb_parts: List[str] = []
        pl_hw_parts: List[str] = []

        for pl_item in pl_items_list:
            if not pl_item:
                continue
            assoc_norm = _normalize_item_number(str(pl_item.get('associated_item', '')))
            matched = False
            if assoc_norm and (
                assoc_norm == part_num_norm or assoc_norm in part_num_norm or part_num_norm in assoc_norm
                or (ocr_orig_norm and (assoc_norm == ocr_orig_norm or assoc_norm in ocr_orig_norm or ocr_orig_norm in assoc_norm))
            ):
                matched = True
            elif not assoc_norm and len(subfolder_results) == 1:
                matched = True
            if matched:
                heb = pl_item.get('pl_summary_hebrew', '')
                if heb and heb not in heb_parts:
                    heb_parts.append(heb)
                pl_hw = pl_item.get('pl_hardware', '')
                if pl_hw and pl_hw not in pl_hw_parts:
                    pl_hw_parts.append(pl_hw)

        if heb_parts:
            result_dict['PL Summary Hebrew'] = ' | '.join(heb_parts)
            logger.info(f"PL Summary Hebrew propagated to '{result_dict.get('part_number','')}': {len(heb_parts)} parts")
        if pl_hw_parts:
            result_dict['PL Hardware'] = ' | '.join(pl_hw_parts)


# ===== internal helpers =====================================================

def _match_pl_items_to_drawings(pl_items_list, subfolder_results, _normalize):
    logger.info(f"Matching {len(pl_items_list)} PL items to {len(subfolder_results)} drawings via associated_item...")
    for pl_item in pl_items_list:
        associated_item = pl_item.get('associated_item', '')
        if not associated_item:
            continue
        associated_norm = _normalize(associated_item)
        for result_dict in subfolder_results:
            part_num = result_dict.get('part_number', '')
            part_num_norm = _normalize(part_num)
            if (associated_norm == part_num_norm
                    or associated_norm in part_num_norm
                    or part_num_norm in associated_norm):
                pl_item['matched_item_name'] = result_dict.get('item_name', part_num)
                pl_item['matched_drawing_part_number'] = part_num
                logger.info(f"PL item → drawing '{result_dict.get('item_name', '')}' (associated: {associated_item})")
                break


def _propagate_pl_main_pn(subfolder_results, pl_items_list, _normalize):
    for result_dict in subfolder_results:
        part_num_norm = _normalize(result_dict.get('part_number', ''))
        for pl_item in pl_items_list:
            assoc_norm = _normalize(pl_item.get('associated_item', ''))
            if (assoc_norm == part_num_norm
                    or assoc_norm in part_num_norm
                    or part_num_norm in assoc_norm):
                pl_pn = pl_item.get('pl_main_part_number', '')
                if pl_pn:
                    result_dict['pl_main_part_number'] = pl_pn
                    break


_INVALID_PN_WORDS = {
    'category', 'description', 'part', 'number', 'rev', 'revision',
    'catalog', 'seq', 'item', 'type', 'make', 'buy', 'qty',
    'status', 'release', 'name', 'unit', 'level', 'none', 'null',
}


def _override_part_numbers(subfolder_results, pl_items_list, _normalize, _extract_base_and_suffix):
    logger.info("PL Part Number Override check...")

    for result_dict in subfolder_results:
        ocr_part_number = result_dict.get('part_number', '')
        ocr_part_normalized = _normalize(ocr_part_number)

        matched_pl = None
        for pl_item in pl_items_list:
            pl_associated = _normalize(pl_item.get('associated_item', ''))
            pl_matched = _normalize(pl_item.get('matched_drawing_part_number', ''))
            if pl_associated and (
                pl_associated == ocr_part_normalized
                or pl_associated in ocr_part_normalized
                or ocr_part_normalized in pl_associated
            ):
                matched_pl = pl_item
                break
            if pl_matched and (
                pl_matched == ocr_part_normalized
                or pl_matched in ocr_part_normalized
                or ocr_part_normalized in pl_matched
            ):
                matched_pl = pl_item
                break

        if not matched_pl:
            continue

        pl_main_pn = matched_pl.get('pl_main_part_number', '')

        if not pl_main_pn or pl_main_pn == 'MULTIPLE':
            if pl_main_pn == 'MULTIPLE':
                result_dict['pl_part_number'] = 'MULTIPLE'
                result_dict['pl_override_note'] = 'PL מכיל מספר פריטים מיוצרים'
            continue

        digit_count = sum(1 for c in pl_main_pn if c.isdigit())
        if digit_count < 3 or len(pl_main_pn) < 6:
            logger.warning(f"⚠️ Skipping PL PN '{pl_main_pn}' — too short or too few digits")
            continue
        if pl_main_pn.upper().startswith('REV'):
            logger.warning(f"⚠️ Skipping PL PN '{pl_main_pn}' — looks like revision, not P.N.")
            continue
        if pl_main_pn.lower() in _INVALID_PN_WORDS or len(pl_main_pn) < 3:
            logger.warning(f"⚠️ Skipping invalid PL part number: '{pl_main_pn}'")
            continue

        pl_main_normalized = _normalize(pl_main_pn)

        if ocr_part_normalized == pl_main_normalized:
            if ocr_part_number.strip() != pl_main_pn.strip():
                old_part = ocr_part_number
                result_dict['part_number_ocr_original'] = old_part
                result_dict['part_number'] = pl_main_pn
                result_dict['pl_part_number'] = pl_main_pn
                result_dict['pl_override_note'] = f'AS PL (OCR: {old_part})'
                dwg = result_dict.get('drawing_number', '')
                if dwg and _normalize(dwg) == _normalize(old_part):
                    base, suffix = _extract_base_and_suffix(pl_main_pn)
                    result_dict['drawing_number'] = base if suffix else pl_main_pn
                logger.info(f"✓ OVERRIDE (dash-number): '{old_part}' → '{pl_main_pn}'")
                continue
            result_dict['pl_part_number'] = pl_main_pn
            result_dict['pl_override_note'] = 'AS PL'
            logger.info(f"✓ CONFIRMED: '{ocr_part_number}' matches PL (AS PL)")
            continue

        old_part = ocr_part_number
        result_dict['part_number_ocr_original'] = old_part
        result_dict['part_number'] = pl_main_pn
        result_dict['pl_part_number'] = pl_main_pn
        result_dict['pl_override_note'] = f'מ-PL (OCR מקורי: {old_part})'
        dwg = result_dict.get('drawing_number', '')
        if dwg and _normalize(dwg) == _normalize(old_part):
            base, suffix = _extract_base_and_suffix(pl_main_pn)
            result_dict['drawing_number'] = base if suffix else pl_main_pn
        logger.info(f"✓ OVERRIDE: '{old_part}' → '{pl_main_pn}' (from PL)")

    overrides = sum(1 for r in subfolder_results if r.get('part_number_ocr_original'))
    if overrides:
        logger.info(f"═══ {overrides} part numbers overridden from PL ═══")
    else:
        logger.info("No overrides needed (OCR matches PL)")


def _update_assoc_after_override(subfolder_results, file_classifications, _normalize):
    override_map: Dict[str, str] = {}
    for result_dict in subfolder_results:
        ocr_original = result_dict.get('part_number_ocr_original', '')
        if ocr_original:
            override_map[_normalize(ocr_original)] = result_dict.get('part_number', '')

    if not override_map:
        return

    for fc in file_classifications:
        assoc = fc.get('associated_item', '')
        assoc_norm = _normalize(assoc)
        if assoc_norm in override_map:
            old_assoc = assoc
            fc['associated_item'] = override_map[assoc_norm]
            logger.info(f"✓ Updated associated_item: '{old_assoc}' → '{fc['associated_item']}'")
