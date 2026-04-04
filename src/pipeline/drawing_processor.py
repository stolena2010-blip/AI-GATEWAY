"""
drawing_processor — Process drawing files through the extraction pipeline.
Extracted from customer_extractor_v3_dual.scan_folder() Phase 2.
"""
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from src.core.cost_tracker import CostTracker
from src.services.extraction.ocr_engine import MultiOCREngine
from src.services.file.file_utils import _get_file_metadata
from src.services.extraction.insert_validator import validate_inserts_hardware
from src.services.extraction.insert_price_lookup import enrich_inserts_with_prices
from src.utils.logger import get_logger

logger = get_logger(__name__)


def process_drawings(
    drawing_files: List[Dict[str, Any]],
    target_folder: Path,
    client,
    ocr_engine: MultiOCREngine,
    cost_tracker: CostTracker,
    selected_stages: Optional[Dict[int, bool]] = None,
    enable_image_retry: bool = False,
    stage1_skip_retry_resolution_px: int = 8000,
    max_file_size_mb: int = 100,
) -> Tuple[List[Dict[str, Any]], float, int, int]:
    """Process drawing files through extract_customer_name.

    Returns:
        (subfolder_results, extraction_cost_accurate, tokens_in, tokens_out)
    """
    from src.services.extraction import ocr_engine as _ocr_mod

    # Filter out files that are too large
    filtered, skipped = _filter_large_files(drawing_files, max_file_size_mb)
    if not filtered:
        return [], 0.0, 0, 0

    logger.info(f"PHASE 2: Processing {len(filtered)} Drawing Files")
    if skipped:
        logger.info(f"Skipped: {len(skipped)} files (too large)")
    logger.info("=" * 70)

    subfolder_results: List[Dict[str, Any]] = []
    cost_accurate = 0.0
    tokens_in_total = 0
    tokens_out_total = 0

    for idx, fc in enumerate(filtered, 1):
        file_path = fc['file_path']
        logger.info(f"[{idx}/{len(filtered)}]  {file_path.name}")

        # GUI stop/skip
        if _ocr_mod._gui_should_stop and _ocr_mod._gui_should_stop():
            logger.info("Stopped by user from GUI")
            raise KeyboardInterrupt
        if _ocr_mod._gui_should_skip and _ocr_mod._gui_should_skip():
            logger.info(f"Skipping {file_path.name} (requested by GUI)")
            import customer_extractor_v3_dual
            if hasattr(customer_extractor_v3_dual, '_gui_skip_reset'):
                customer_extractor_v3_dual._gui_skip_reset()
            continue

        cost_tracker.total_files += 1
        file_start = time.time()

        try:
            from customer_extractor_v3_dual import extract_customer_name
            data, usage = extract_customer_name(
                str(file_path), client, ocr_engine,
                selected_stages=selected_stages,
                enable_retry=enable_image_retry,
                stage1_skip_retry_resolution_px=stage1_skip_retry_resolution_px,
            )

            # GUI skip after processing
            if _ocr_mod._gui_should_skip and _ocr_mod._gui_should_skip():
                logger.info(f"Skipping {file_path.name} (requested by GUI)")
                import customer_extractor_v3_dual
                if hasattr(customer_extractor_v3_dual, '_gui_skip_reset'):
                    customer_extractor_v3_dual._gui_skip_reset()
                continue

        except KeyboardInterrupt:
            logger.info("Ctrl+C pressed!")
            logger.info("[S] Skip  [Q] Quit  [C] Continue")
            choice = input("   Your choice (S/Q/C): ").strip().upper()
            if choice == 'S':
                logger.info(f"Skipping {file_path.name}...")
                continue
            elif choice == 'Q':
                logger.info("Stopped by user")
                raise KeyboardInterrupt
            else:
                data, usage = extract_customer_name(
                    str(file_path), client, ocr_engine,
                    selected_stages=selected_stages,
                    enable_retry=enable_image_retry,
                    stage1_skip_retry_resolution_px=stage1_skip_retry_resolution_px,
                )
        except Exception as file_error:
            logger.error(f"❌ FAILED to process {file_path.name}: {file_error}", exc_info=True)
            continue

        file_time = time.time() - file_start
        file_cost = 0.0

        if usage:
            file_cost = (data.get('_pipeline_cost_usd') or 0) if data else 0
            if not file_cost:
                from src.services.ai import ModelRuntimeConfig as _MRC
                _rt = _MRC.from_env()
                file_cost = (usage[0] / 1_000_000 * _rt.input_price_per_1m) + (usage[1] / 1_000_000 * _rt.output_price_per_1m)
            cost_tracker.add_usage(usage[0], usage[1], cost=file_cost)
            tokens_in_total += usage[0]
            tokens_out_total += usage[1]
            cost_accurate += file_cost

        logger.info(f"Runtime: {file_time:.2f}s | Cost: ${file_cost:.4f}")

        try:
            if data and isinstance(data, dict):
                cost_tracker.successful_files += 1
                data['execution_time_seconds'] = round(file_time, 2)
                data['extraction_cost_usd'] = round(file_cost, 4)
                data.pop('_pipeline_cost_usd', None)

                result_dict = _build_result_dict(data, file_path, target_folder)
                subfolder_results.append(result_dict)
        except Exception as result_error:
            logger.error(f"❌ FAILED to build result for {file_path.name}: {result_error}", exc_info=True)

    return subfolder_results, cost_accurate, tokens_in_total, tokens_out_total


def _filter_large_files(
    drawing_files: List[Dict[str, Any]],
    max_file_size_mb: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split drawing_files into (processable, skipped_too_large)."""
    filtered = []
    skipped = []
    for fc in drawing_files:
        metadata = _get_file_metadata(fc['file_path'])
        if metadata['is_too_large']:
            skipped.append({'file': fc['file_path'].name, 'size_mb': metadata['file_size_mb']})
            logger.info(f"SKIPPING (too large): {fc['file_path'].name} ({metadata['file_size_mb']}MB)")
        else:
            if metadata['is_large_file']:
                logger.warning(f"WARNING (large file): {fc['file_path'].name} ({metadata['file_size_mb']}MB)")
            filtered.append(fc)
    return filtered, skipped


def _build_result_dict(data: Dict[str, Any], file_path: Path, target_folder: Path) -> Dict[str, Any]:
    """Build the standardized result dictionary from extraction data."""
    return {
        "file_name": file_path.name,
        "customer_name": data.get("customer_name") or "",
        "part_number": data.get("part_number") or "",
        "item_name": data.get("item_name") or "",
        "drawing_number": data.get("drawing_number") or "",
        "revision": data.get("revision") or "",
        "needs_review": data.get("needs_review") or "",
        "confidence_level": data.get("confidence_level") or "",
        "material": data.get("material") or "",
        "coating_processes": data.get("coating_processes") or "",
        "painting_processes": data.get("painting_processes") or "",
        "colors": data.get("colors") or "",
        "part_area": data.get("part_area") or "",
        "specifications": data.get("specifications") or "",
        "parts_list_page": data.get("parts_list_page") or "",
        "inserts_hardware": enrich_inserts_with_prices(
            validate_inserts_hardware(
                data.get("inserts_hardware") or [],
                part_number=data.get("part_number") or data.get("drawing_number") or "",
            )
        ),
        "process_summary_hebrew": data.get("process_summary_hebrew") or "",
        "process_summary_hebrew_short": data.get("process_summary_hebrew_short") or "",
        "notes_full_text": data.get("notes_full_text") or "",
        "num_pages": data.get("num_pages") or 1,
        # Quantities — filled later by quantity matching
        "quantity": "",
        "quantity_match_type": "",
        "quantity_source": "",
        "work_description_doc": "",
        "work_description_email": "",
        # Email — filled later
        "email_from": "",
        "email_subject": "",
        # Technical metadata
        "subfolder": target_folder.name,
        "validation_warnings": data.get("validation_warnings") or "",
        "image_resolution": data.get("image_resolution") or "",
        "drawing_layout": data.get("drawing_layout") or "",
        "quality_issues": data.get("quality_issues") or "",
        "execution_time_seconds": data.get("execution_time_seconds") or 0,
        "extraction_cost_usd": data.get("extraction_cost_usd") or 0,
    }
