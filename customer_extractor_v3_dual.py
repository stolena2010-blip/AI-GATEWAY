"""
Customer Name Extractor from Drawings - QUAD-STAGE VERSION + FILE CLASSIFICATION
==================================================================================

שיפורים בגרסה זו:
 שלב מקדים: זיהוי אוטומטי של סוג קבצים (שרטוטים vs מסמכים אחרים)
 חיסכון בעלויות - עיבוד רק של שרטוטים
 דוח מפורט של כל הקבצים בתיקייה
 חילוץ בשני שלבים נפרדים לדיוק מקסימלי
 שלב 1: זיהוי בסיסי (לקוח, פריט, שרטוט, גרסה, חומר)
 שלב 2: תהליכים ומפרטים (ציפוי, צביעה, מפרטים)
 OCR עם Tesseract + עיבוד תמונה מתקדם
 מעקב אחר עלויות מדויק

Usage:
    python customer_extractor_v3_dual.py [optional_folder_path]
"""

import os
import sys
import re
import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
import zipfile
import subprocess

from dotenv import load_dotenv
from openai import AzureOpenAI
import pandas as pd
import pdfplumber
from src.services.ai import ModelRuntimeConfig
from src.services.image.processing import (
    _downsample_high_res_image,
    _enhance_contrast_for_title_block,
    _extract_image_smart,
    _assess_image_quality,
    _apply_rotation_angle,
    _fix_image_rotation,
)
from src.services.ai.vision_api import (
    _build_client,
    _resolve_stage_call_config,
    _calculate_stage_cost,
    _chat_create_with_token_compat,
    _call_vision_api_with_retry,
)
from src.services.extraction.filename_utils import (
    check_value_in_filename,
    check_exact_match_in_filename,
    _disambiguate_part_number,
    _normalize_item_number,
    _fuzzy_substring_match,
    extract_part_number_from_filename,
    _extract_item_number_from_filename,
)
from src.services.extraction.pn_voting import (
    deduplicate_line,
    extract_pn_dn_from_text as _extract_pn_dn_from_text,
    vote_best_pn as _vote_best_pn,
)
from src.services.extraction.sanity_checks import (
    is_cage_code,
    run_pn_sanity_checks,
    calculate_confidence,
)
from src.services.extraction.post_processing import (
    post_process_summary_from_notes as _post_process_summary_from_notes,
)
from src.services.extraction.quantity_matcher import (
    match_quantities_to_drawings as _match_quantities_to_drawings,
    extract_base_and_suffix as _extract_base_and_suffix,
    override_pn_from_email as _override_pn_from_email,
)
from src.services.reporting.b2b_export import (
    _save_text_summary_with_variants,
)
from src.services.reporting.pl_generator import (
    extract_pl_data,
)
from src.services.reporting.excel_export import (
    _save_classification_report,
    _update_pl_sheet_with_associated_items,
    _save_results_to_excel,
)
from src.services.file.file_utils import (
    _find_associated_drawing,
)
from src.services.file.classifier import classify_file_type
from src.services.file.file_renamer import rename_files_by_classification as _rename_files_by_classification
from src.pipeline.archive_extractor import extract_archives_in_folders
from src.pipeline.drawing_processor import process_drawings
from src.pipeline.pl_processor import update_pl_associations, extract_and_process_pl, propagate_pl_data
from src.pipeline.folder_saver import save_folder_output
from src.pipeline.results_merger import merge_all_results, copy_folders_to_tosend, print_final_summary
from src.services.extraction.document_reader import (
    _read_email_content,
    _extract_item_details_from_documents,
)
from src.services.extraction.stage9_merge import (
    merge_descriptions as _merge_descriptions,
)

from src.utils.logger import get_logger

# ספריות עיבוד תמונה ו-OCR
import cv2
import numpy as np
from PIL import Image

# Load environment variables
load_dotenv()

# Ensure Unicode-safe console output (important on Windows cp1255/cp1252 terminals)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logger = get_logger(__name__)

MODEL_RUNTIME = ModelRuntimeConfig.from_env()
AZURE_DEPLOYMENT = MODEL_RUNTIME.deployment
DRAWING_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}

# Pricing from runtime configuration (.env)
MODEL_INPUT_PRICE_PER_1M = MODEL_RUNTIME.input_price_per_1m
MODEL_OUTPUT_PRICE_PER_1M = MODEL_RUNTIME.output_price_per_1m

# Per-stage model mapping (configurable in .env via STAGE_{N}_*)
STAGE_CLASSIFICATION = 0
STAGE_LAYOUT = 0
STAGE_ROTATION = 0
STAGE_BASIC_INFO = 1
STAGE_PROCESSES = 2
STAGE_NOTES = 3
STAGE_AREA = 4
STAGE_VALIDATION = 5
STAGE_PL = 6
STAGE_EMAIL_QUANTITIES = 7
STAGE_ORDER_ITEM_DETAILS = 8
STAGE_DESCRIPTION_MERGE = 9


STAGE_DISPLAY_NAMES = {
    STAGE_CLASSIFICATION: "Stage 0 (Classification/Layout/Rotation)",
    STAGE_BASIC_INFO: "Stage 1 (Basic Info)",
    STAGE_PROCESSES: "Stage 2 (Processes)",
    STAGE_NOTES: "Stage 3 (Notes)",
    STAGE_AREA: "Stage 4 (Area)",
    STAGE_VALIDATION: "Stage 5 (Validation)",
    STAGE_PL: "Stage 6 (PL)",
    STAGE_EMAIL_QUANTITIES: "Stage 7 (Email Quantities)",
    STAGE_ORDER_ITEM_DETAILS: "Stage 8 (Quote/Order Item Details)",
    STAGE_DESCRIPTION_MERGE: "Stage 9 (Description Merge)",
}
# File size limits (in MB)
MAX_FILE_SIZE_MB = 100  # Skip files larger than this
WARN_FILE_SIZE_MB = 50  # Warn about files larger than this

# Image resolution limits (in pixels)
MAX_IMAGE_DIMENSION = 4096  # Maximum width or height in pixels
TARGET_IMAGE_DIMENSION = 2048  # Target dimension for downsampling high-res images
WARN_IMAGE_DIMENSION = 3000  # Warn about images larger than this

#  Structured JSON output
RESPONSE_FORMAT = {"type": "json_object"}

# ── Internal modules (split from this file) ──
from src.services.extraction import ocr_engine as _ocr_mod
from src.services.extraction.ocr_engine import (
    debug_print,
    MultiOCREngine,
    extract_stage1_with_retry,
    DEBUG_ENABLED,
    IAI_TOP_RED_FALLBACK_ENABLED,
    set_gui_callbacks,
)
from src.core.cost_tracker import CostTracker
from src.services.extraction.stages_generic import (
    identify_drawing_layout,
    extract_basic_info,
    extract_processes_info,
    validate_notes_before_stage5,
    extract_notes_text,
    calculate_geometric_area,
)
from src.services.extraction.stages_rafael import (
    identify_drawing_layout_rafael,
    extract_basic_info_rafael,
    extract_processes_info_rafael,
    extract_processes_from_notes,
    extract_notes_text_rafael,
    extract_area_info_rafael,
)
from src.services.extraction.stages_iai import (
    _extract_iai_top_red_identifier,
    identify_drawing_layout_iai,
    extract_basic_info_iai,
    extract_processes_info_iai,
    extract_notes_text_iai,
    extract_area_info_iai,
)



# ── Functions moved to src/services/extraction/ ──
# _post_process_summary_from_notes → post_processing.py
# _extract_pn_dn_from_text, _vote_best_pn → pn_voting.py
# extract_drawing_data, _run_with_timeout → drawing_pipeline.py


def extract_customer_name(file_path: str, client: AzureOpenAI, ocr_engine: MultiOCREngine, selected_stages: Optional[Dict[int, bool]] = None, enable_retry: bool = False, stage1_skip_retry_resolution_px: int = 8000) -> Tuple[Optional[Dict], Optional[Tuple[int, int]]]:
    """
     חילוץ מידע בארבעה שלבים
     בוחר אוטומטית בין מודל רפאל למודל סטנדרטי
    
    Args:
        file_path: Path to drawing file
        client: Azure OpenAI client
        ocr_engine: OCR engine
        selected_stages: Dict of which stages to run {1: True, 2: False, 3: True, 4: True}
    """
    from src.services.extraction.drawing_pipeline import extract_drawing_data

    # Default: run all stages
    if selected_stages is None:
        selected_stages = {1: True, 2: True, 3: True, 4: True}

    # ── Run the full pipeline (Stages 0-4 + post-processing + P.N. voting) ──
    result_data, token_counts, context = extract_drawing_data(
        file_path=file_path,
        client=client,
        ocr_engine=ocr_engine,
        selected_stages=selected_stages,
        enable_retry=enable_retry,
        stage1_skip_retry_resolution_px=stage1_skip_retry_resolution_px,
    )

    if result_data is None:
        return None, None

    # ── Sanity checks (uses context from pipeline) ───────────────
    filename = Path(file_path).stem
    result_data = run_pn_sanity_checks(
        result_data,
        filename=filename,
        file_path=file_path,
        pdfplumber_text=context.get('pdfplumber_text', ''),
        is_rafael=context.get('is_rafael', False),
        is_iai=context.get('is_iai', False),
    )

    # Add metadata
    result_data['num_pages'] = context.get('num_pages', 1)

    # Calculate confidence
    result_data = calculate_confidence(result_data, filename, file_path)

    part_in_filename = result_data.get('part_in_filename', False)
    drawing_in_filename = result_data.get('drawing_in_filename', False)

    # Display results
    if result_data.get('customer_name'):
        logger.info(f"Customer: {result_data['customer_name']}")
    if result_data.get('part_number'):
        status = "✅" if part_in_filename else "⚠️"
        quality_flag = "  [בעייתי]" if result_data.get('needs_review') else ""
        logger.info(f"{status} Part#: {result_data['part_number']}{quality_flag} {'(in filename)' if part_in_filename else '(NOT in filename!)'}")
    if result_data.get('item_name'):
        logger.info(f"Item Name: {result_data['item_name']}")
    if result_data.get('drawing_number'):
        status = "✅" if drawing_in_filename else "⚠️"
        logger.info(f"{status} Drawing#: {result_data['drawing_number']} {'(in filename)' if drawing_in_filename else '(NOT in filename!)'}")
    if result_data.get('revision'):
        logger.info(f"Revision: {result_data['revision']}")
    if result_data.get('material'):
        logger.info(f"Material: {result_data['material']}")
    if result_data.get('coating_processes'):
        logger.info(f"Coating: {result_data['coating_processes']}")
    if result_data.get('painting_processes'):
        logger.info(f"Painting: {result_data['painting_processes']}")
    if result_data.get('colors'):
        logger.info(f"Colors: {result_data['colors']}")
    if result_data.get('marking_process'):
        logger.info(f"Marking: {result_data['marking_process']}")
    if result_data.get('part_area'):
        logger.info(f"Area: {result_data['part_area']}")
    if result_data.get('specifications'):
        logger.info(f"Specifications: {result_data['specifications']}")
    if result_data.get('parts_list_page'):
        logger.info(f"Parts List: page {result_data['parts_list_page']}")
    if result_data.get('process_summary_hebrew'):
        logger.info(f"Summary: {result_data['process_summary_hebrew']}")
    if result_data.get('notes_full_text'):
        preview = result_data['notes_full_text'][:100].replace('\n', ' ')
        logger.info(f"Notes: {preview}...")

    # Clean up internal flags before returning
    result_data.pop('_searched_for_pn_field', None)
    result_data.pop('validation_warnings', None)

    # Pass accurate per-stage cost to caller
    if context and 'pipeline_cost_usd' in context:
        result_data['_pipeline_cost_usd'] = context['pipeline_cost_usd']

    return result_data, token_counts


# 
# Folder Scanning
# 
# Folder Scanning
# 

def scan_folder(
    folder_path: Path,
    recursive: bool = True,
    after_date: Optional[datetime] = None,
    date_range: Optional[tuple] = None,
    selected_stages: Optional[Dict[int, bool]] = None,
    enable_image_retry: bool = False,
    tosend_folder: Optional[str] = None,
    confidence_level: str = "LOW",
    stage1_skip_retry_resolution_px: int = 8000,
    max_file_size_mb: Optional[int] = None,
    max_image_dimension: Optional[int] = None,
    profile_config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Scan folder for drawings
    
    Args:
        confidence_level: B2B file confidence filter - "LOW" (all rows), "MEDIUM" (MEDIUM+HIGH+FULL), "HIGH" (HIGH+FULL only)
        profile_config: Optional flat config dict (from _normalize_profile_config).
                        When provided, prompts_folder is extracted and set as thread-local
                        context so all downstream load_prompt() calls use the correct folder.
    """
    global MAX_FILE_SIZE_MB, MAX_IMAGE_DIMENSION

    # ── Set prompts context from profile config ───────────────────
    _prompts_folder = None
    if profile_config:
        _prompts_folder = profile_config.get("prompts_folder") or None
    from src.utils.prompt_loader import set_prompts_context
    set_prompts_context(_prompts_folder)
    if _prompts_folder:
        logger.info(f"📂 Prompts folder: {_prompts_folder}")

    try:
        if max_file_size_mb is not None:
            MAX_FILE_SIZE_MB = max(int(max_file_size_mb), 1)
    except Exception:
        pass

    try:
        if max_image_dimension is not None:
            MAX_IMAGE_DIMENSION = max(int(max_image_dimension), 256)
    except Exception:
        pass

    # Default: run all stages
    if selected_stages is None:
        selected_stages = {1: True, 2: True, 3: True, 4: True}
    folder_path = folder_path.resolve()
    if not folder_path.exists():
        logger.info(f"Folder not found: {folder_path}")
        set_prompts_context(None)
        return [], folder_path, None, {}
    
    logger.info(f"Scanning folder: {folder_path}")
    logger.info(f"{'(including subfolders)' if recursive else '(no subfolders)'}")
    confidence_descriptions = {'LOW': 'כל השורות', 'MEDIUM': 'בינוני+גבוה+מלא', 'HIGH': 'גבוה בלבד'}
    desc = confidence_descriptions.get(confidence_level, confidence_level)
    logger.info(f"📊 B2B file confidence filter: {confidence_level} ({desc})")
    
    skip_dirs = {".venv", "venv", "env", "__pycache__", ".git", "node_modules"}
    
    # 
    # שלב 0: איסוף תת-תיקיות
    # 
    subfolders_to_process = []
    
    if recursive:
        # Collect all subfolders (including root)
        for root, dirs, _ in os.walk(folder_path):
            dirs[:] = [d for d in dirs if d.lower() not in skip_dirs]
            subfolders_to_process.append(Path(root))
    else:
        # Only root folder
        subfolders_to_process.append(folder_path)
    
    if not subfolders_to_process:
        logger.info("No folders to process")
        return [], folder_path, None, {}

    # 
    # שלב 0.5: פתיחת קובצי ZIP ו-RAR אל תוך התיקיות
    # 
    extract_archives_in_folders(subfolders_to_process)
    
    logger.info(f"[FOLDER] Found {len(subfolders_to_process)} folder(s) to process\n")
    
    # Create NEW FILES output folder
    project_folder = Path(__file__).parent
    output_folder = project_folder / "NEW FILES"
    output_folder.mkdir(exist_ok=True)
    
    # Initialize Azure OpenAI client once
    logger.info("[SETUP] Initializing Azure OpenAI client...")
    client = _build_client()
    logger.info(f"[AI] Azure OpenAI: {AZURE_DEPLOYMENT}\n")
    
    cost_tracker = CostTracker(MODEL_INPUT_PRICE_PER_1M, MODEL_OUTPUT_PRICE_PER_1M)
    ocr_engine = MultiOCREngine()
    
    # Track execution time
    start_time = time.time()
    
    logger.info("[TIP] Press Ctrl+C during processing to skip the current file or stop")
    
    logger.info(f"[OUTPUT] Output folder: {output_folder}")
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    
    # נשמור נתונים לאיחוד בסוף
    all_results = []
    all_classifications = []
    folder_classifications_map = {}  # {target_folder: file_classifications} for TOSEND copy
    total_rafael_rows = 0
    skipped_large_files = []
    
    # Global classification tracking
    global_classification_tokens_in = 0
    global_classification_tokens_out = 0
    global_classification_time = 0  # Total classification time across all folders
    classification_folder_count = 0  # Number of folders where classification occurred
    
    # Global Stage 6 (PL extraction) tracking
    global_stage6_tokens_in = 0
    global_stage6_tokens_out = 0
    
    # Track per-folder statistics for GUI display
    folder_stats = []
    
    # Wrap main processing loop in try-except to handle Ctrl+C gracefully
    try:
        # 
        # עיבוד כל תת-תיקייה בנפרד
        # 
        for folder_idx, target_folder in enumerate(subfolders_to_process, 1):
            logger.debug(f"\n✓ DEBUG: Starting folder loop iteration {folder_idx}")
            logger.info(f"Target folder: {target_folder.name}")
            
            folder_start_time = time.time()  # Track total time for this folder
            folder_classification_cost = 0
            folder_extraction_cost = 0
            folder_extraction_cost_accurate = 0.0  # Per-stage accurate cost accumulator
            folder_extraction_tokens_in = 0  # Track extraction tokens for this folder
            folder_extraction_tokens_out = 0  # Track extraction tokens for this folder
            folder_stage6_tokens_in = 0  # Track Stage 6 (PL) tokens for this folder
            folder_stage6_tokens_out = 0  # Track Stage 6 (PL) tokens for this folder
            subfolder_results = []  # Initialize here to avoid undefined variable error
            drawing_results = subfolder_results
            pl_items_list = []  # Initialize PL items list (will be populated in Stage 6)
            
            logger.info(f"{'='*70}")
            logger.info(f"Folder {folder_idx}/{len(subfolders_to_process)}: {target_folder.name}")
            logger.info(f"{'='*70}")
            
            # 
            # שלב 1: איסוף קבצים בתיקייה זו בלבד
            # 
            folder_files = []
            skipped_by_date = 0
            
            for file_path in target_folder.iterdir():
                if file_path.is_file():
                    name = file_path.name
                    if name.startswith('.') or name.startswith('~'):
                        continue
                    # Apply date filter
                    if date_range or after_date:
                        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if date_range:
                            date_from, date_to = date_range
                            if not (date_from <= file_mtime <= date_to):
                                skipped_by_date += 1
                                continue
                        elif after_date:
                            if file_mtime < after_date:
                                skipped_by_date += 1
                                continue
                    folder_files.append(file_path)
            
            if skipped_by_date > 0:
                logger.info(f"Skipped {skipped_by_date} files (by date filter)")
            
            if not folder_files:
                logger.info(f"No files in this folder - skipping")
                continue
            
            logger.info(f"Found {len(folder_files)} files in folder\n")
            
            # 
            # שלב 2: זיהוי סוג כל קובץ בתיקייה זו
            # 
            logger.info("PHASE 1: File Type Classification")
            logger.info("=" * 70)
            
            classification_start_time = time.time()  # Track classification time for this folder
            file_classifications = []
            classification_tokens_in = 0
            classification_tokens_out = 0
            
            for idx, file_path in enumerate(folder_files, 1):
                logger.info(f"[{idx}/{len(folder_files)}]  {file_path.name}")
                
                file_type, description, quote_number, order_number, tokens_in, tokens_out = classify_file_type(str(file_path), client)
                
                classification_tokens_in += tokens_in
                classification_tokens_out += tokens_out
                
                # Skip ARCHIVE files - they will be extracted in Phase 0.5
                if file_type == 'ARCHIVE':
                    logger.info(f"Archive file - skipped (will be extracted automatically)")
                    continue
                
                # Extract item_number and revision for DISPLAY NAME
                item_number = ''
                revision = ''
                drawing_number = ''
                part_number = ''
                display_name = ''
                associated_item = ''  # Initialize for ALL files (will be set for PARTS_LIST linking)
                
                # תיקון חזק: אם קובץ הוא תמונה בפועל (jpg, png וכו'), תיקון הסיווג ל-3D_IMAGE
                ext_lower = file_path.suffix.lower()
                if ext_lower in {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif', '.webp'}:
                    if file_type != '3D_IMAGE':
                        logger.info(f"🔧 Correcting file type for {file_path.name}: {file_type} → 3D_IMAGE")
                        file_type = '3D_IMAGE'
                
                # For DRAWING type (_30), try to find drawing_number and revision from drawing_results
                if file_type == 'DRAWING' and drawing_results:
                    file_name = file_path.name
                    for dr in drawing_results:
                        if dr.get('file_name') == file_name:
                            drawing_number = dr.get('drawing_number', '')
                            part_number = dr.get('part_number', '')
                            revision = dr.get('revision', '')
                            item_number = drawing_number
                            if drawing_number and part_number:
                                # For drawings: drawing_number + TAB + part_number + TAB + revision + TAB (no extension)
                                display_name = f"{drawing_number} \t{part_number} \t{revision} \t"
                            break
                # For other types (_99), use filename + quote_number/order_number + revision
                elif file_type in ['PURCHASE_ORDER', 'QUOTE', 'INVOICE', 'PARTS_LIST', '3D_MODEL', '3D_IMAGE', 'OTHER']:
                    if quote_number:
                        item_number = quote_number
                    elif order_number:
                        item_number = order_number
                    
                    # Try to find associated drawing for non-drawing files
                    # This gives us drawing_number and revision from the related drawing
                    if drawing_results and file_type in ['PARTS_LIST', '3D_MODEL', 'OTHER']:
                        # Build drawing map for filename matching
                        temp_drawing_map = {}
                        for dr in drawing_results:
                            dr_file = dr.get('file_name', '')
                            dr_drawing_num = dr.get('drawing_number', '')
                            dr_part_num = dr.get('part_number', '')
                            dr_rev = dr.get('revision', '')
                            if dr_file and dr_part_num:
                                temp_drawing_map[dr_file] = {
                                    'part_number': dr_part_num,
                                    'drawing_number': dr_drawing_num,
                                    'revision': dr_rev
                                }
                        
                        # Find associated drawing by filename similarity
                        if temp_drawing_map:
                            associated_part = _find_associated_drawing(file_path, file_type, temp_drawing_map)
                            if associated_part:
                                # Find the drawing with this part_number to get drawing_number and revision
                                for dr in drawing_results:
                                    if dr.get('part_number', '') == associated_part:
                                        drawing_number = dr.get('drawing_number', '')
                                        revision = dr.get('revision', '')
                                        item_number = associated_part
                                        associated_item = associated_part  # Store for PL linking (Stage 6)
                                        break
                    
                    # For non-drawing files: build display_name
                    if item_number:
                        if file_type in ('3D_MODEL', '3D_IMAGE'):
                            # Same structure as DRAWING but with file extension at the end
                            file_ext = file_path.suffix
                            display_name = f"{drawing_number} \t{item_number} \t{revision} \t{file_ext}"
                        else:
                            original_name_no_ext = file_path.stem
                            display_name = f"{original_name_no_ext} \t{item_number} \t{revision} \t"
                
                file_classifications.append({
                    'file_path': file_path,
                    'original_filename': file_path.name,
                    'file_type': file_type,
                    'description': description,
                    'quote_number': quote_number if quote_number else '',
                    'order_number': order_number if order_number else '',
                    'item_number': item_number,
                    'revision': revision,
                    'drawing_number': drawing_number,
                    'part_number': part_number,
                    'associated_item': associated_item,
                    'display_name': display_name
                })
                
                # Display classification
                icon = {
                    'DRAWING': '',
                    'PURCHASE_ORDER': '',
                    'QUOTE': '',
                    'INVOICE': '',
                    'PARTS_LIST': '',
                    '3D_MODEL': '',
                    'ARCHIVE': '📦',
                    'OTHER': ''
                }.get(file_type, '')
                
                logger.info(f"{icon} Type: {file_type}")
                if description:
                    logger.info(f"{description}")
                if file_type == 'QUOTE' and quote_number:
                    logger.info(f"Quote Number: {quote_number}")
                if file_type in ['PURCHASE_ORDER', 'INVOICE'] and order_number:
                    logger.info(f"Order Number: {order_number}")
            
            # Add to global tracking
            classification_end_time = time.time()
            classification_elapsed = classification_end_time - classification_start_time
            global_classification_tokens_in += classification_tokens_in
            global_classification_tokens_out += classification_tokens_out
            global_classification_time += classification_elapsed
            classification_folder_count += 1
            
            # Statistics for this folder
            logger.info("" + "=" * 70)
            logger.info("Classification Summary (this folder):")
            logger.info("=" * 70)
            
            from collections import Counter
            type_counts = Counter(fc['file_type'] for fc in file_classifications)
            
            for file_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                icon = {
                    'DRAWING': '',
                    'PURCHASE_ORDER': '',
                    'QUOTE': '',
                    'INVOICE': '',
                    'PARTS_LIST': '',
                    '3D_MODEL': '',
                    'ARCHIVE': '📦',
                    'OTHER': ''
                }.get(file_type, '')
                logger.info(f"{icon} {file_type}: {count}")
            
            logger.info(f"Classification cost (this folder):")
            class_input_cost = (classification_tokens_in / 1_000_000) * MODEL_RUNTIME.get_stage_input_price(STAGE_CLASSIFICATION)
            class_output_cost = (classification_tokens_out / 1_000_000) * MODEL_RUNTIME.get_stage_output_price(STAGE_CLASSIFICATION)
            class_total_cost = class_input_cost + class_output_cost
            folder_classification_cost = class_total_cost  # Store for folder stats
            logger.info(f"Input:  {classification_tokens_in:,} tokens (${class_input_cost:.4f})")
            logger.info(f"Output: {classification_tokens_out:,} tokens (${class_output_cost:.4f})")
            logger.info(f"Total:  ${class_total_cost:.4f} USD ({class_total_cost * 3.7:.2f})")
            logger.info(f"Time: {classification_elapsed:.1f} seconds")
            logger.info("=" * 70)
            
            # 
            # שלב 3: עיבוד שרטוטים בתיקייה זו
            # 
            # Filter for drawing files - safely handle None and invalid entries
            drawing_files = [fc for fc in file_classifications if fc and isinstance(fc, dict) and fc.get('file_type') == 'DRAWING']
            
            if not drawing_files:
                logger.info(f"No drawing files in this folder - skipping to next folder")
                # Still save classification for this folder (filter out None values)
                all_classifications.extend([fc for fc in file_classifications if fc and isinstance(fc, dict)])
                
                # Collect folder statistics even if no drawings
                from collections import Counter
                file_type_counts = Counter(fc.get('file_type', 'UNKNOWN') for fc in file_classifications if fc and isinstance(fc, dict))
                
                folder_end_time = time.time()
                folder_total_time = folder_end_time - folder_start_time
                
                folder_info = {
                    'name': target_folder.name,
                    'total_files': len(file_classifications),
                    'file_types': dict(file_type_counts),
                    'total_drawings': 0,
                    'confidence_high': 0,
                    'confidence_medium': 0,
                    'confidence_low': 0,
                    'classification_cost': folder_classification_cost,
                    'extraction_cost': 0,
                    'total_cost': folder_classification_cost,
                    'processing_time': folder_total_time
                }
                folder_stats.append(folder_info)
                
                continue
            
            # Process drawing files through extraction pipeline
            new_results, ext_cost, ext_tokens_in, ext_tokens_out = process_drawings(
                drawing_files, target_folder, client, ocr_engine, cost_tracker,
                selected_stages=selected_stages,
                enable_image_retry=enable_image_retry,
                stage1_skip_retry_resolution_px=stage1_skip_retry_resolution_px,
                max_file_size_mb=MAX_FILE_SIZE_MB,
            )
            subfolder_results.extend(new_results)
            folder_extraction_cost_accurate += ext_cost
            folder_extraction_tokens_in += ext_tokens_in
            folder_extraction_tokens_out += ext_tokens_out
            
            if not subfolder_results and drawing_files:
                # All drawing files were filtered out (too large) or failed
                all_classifications.extend([fc for fc in file_classifications if fc and isinstance(fc, dict)])
                
                from collections import Counter
                file_type_counts = Counter(fc.get('file_type', 'UNKNOWN') for fc in file_classifications if fc and isinstance(fc, dict))
                
                folder_end_time = time.time()
                folder_total_time = folder_end_time - folder_start_time
                
                folder_info = {
                    'name': target_folder.name,
                    'total_files': len(file_classifications),
                    'file_types': dict(file_type_counts),
                    'total_drawings': len(drawing_files),
                    'confidence_high': 0,
                    'confidence_medium': 0,
                    'confidence_low': 0,
                    'classification_cost': folder_classification_cost,
                    'extraction_cost': 0,
                    'total_cost': folder_classification_cost,
                    'processing_time': folder_total_time
                }
                folder_stats.append(folder_info)
                
                continue
            
            # 
            # שלב 2: התאמת כמויות ותיאורים לאחר עיבוד כל השרטוטים
            # 
            # Defaults to avoid undefined variables when no drawings/email
            email_data = {
                'found': False,
                'subject': '',
                'general_quantities': [],
                'part_quantities': {},
                'work_description': '',
                'quantity_summary': ''
            }
            item_details = {}
            if subfolder_results:
                logger.info(f"[STAGE2] Stage 2: Match quantities and descriptions ({len(subfolder_results)} items)...")
                
                # קרא קובץ email אם קיים
                email_data = _read_email_content(target_folder, client)
            
            # Step 1: חלץ כמויות ותיאורי עבודה מהזמנות/הצעות
            # Ensure file_classifications is not None before passing to extraction function
            if file_classifications is None:
                logger.debug(f"DEBUG: file_classifications is None - skipping item details extraction")
                file_classifications = []
            
            item_details = _extract_item_details_from_documents(
                target_folder, file_classifications, client, email_data=email_data
            )
            
            # Step 2: PL processing moved to Stage 6 (separate workflow)
            
            general_quantities = []
            if email_data and email_data.get('found'):
                logger.info(f"Email: {email_data.get('subject', '')[:50]}...")
                general_quantities = email_data.get('general_quantities', [])
                if general_quantities:
                    logger.info(f"General quantities from email: {', '.join(general_quantities)}")
                
                if item_details:  # Only iterate if item_details is not empty
                    for key in item_details.keys():
                        if isinstance(item_details[key], dict) and 'quantities' in item_details[key]:
                            logger.info(f"'{key}' -> Qty: {item_details[key]['quantities']}")

                

            logger.debug(f"\nDEBUG: After processing drawings, subfolder_results = {len(subfolder_results)}")
            if len(subfolder_results) == 0:
                logger.debug("DEBUG: WARNING - NO RESULTS FROM DRAWING PROCESSING!")

            items_with_specific_qty, items_with_general_qty = _match_quantities_to_drawings(
                subfolder_results, item_details, email_data, general_quantities, pl_items_list
            )
            
            #  Fallback: match by PL filename for items without match
            logger.info("Trying PL filename matching for items without a match...")
            for pl_item in pl_items_list:
                if pl_item.get('matched_drawing'):
                    continue  # כבר יש התאמה
                
                # חלץ את חלק שם הקובץ (הסר .pdf וסיומות אחרות)
                pl_filename = pl_item.get('pl_filename', '')
                # הסר סיומות קובץ ותוויות revision (_a, _b, וכו')
                pl_filename_core = re.sub(r'\.[^.]*$', '', pl_filename)  # הסר .pdf/.xlsx וכו'
                pl_filename_core = re.sub(r'_[a-z]$', '', pl_filename_core, flags=re.IGNORECASE)  # הסר _a, _b וכו'
                # נרמל את שם קובץ ה-PL
                pl_filename_normalized = _normalize_item_number(pl_filename_core)
                
                # חפש התאמה בשרטוטים
                for result_dict in subfolder_results:
                    part_num = result_dict.get('part_number', '')
                    part_num_normalized = _normalize_item_number(part_num)
                    
# אם part_number משרטוט מופיע בשם קובץ ה-PL (עם עדינויות OCR)
                    if part_num_normalized and len(part_num_normalized) >= 5:
                        # בדוק שני כיוונים עם fuzzy matching (מטפל ב-O/0, I/1, l/1):
                        if (_fuzzy_substring_match(part_num_normalized, pl_filename_normalized) or
                            _fuzzy_substring_match(pl_filename_normalized, part_num_normalized)):
                            drawing_name = result_dict.get('file_name', '')
                            pl_item['matched_drawing'] = drawing_name
                            logger.info(f"Matched by PL filename: '{pl_item['part_number']}'  '{drawing_name}' (via '{pl_filename}')")
                            break
            
            logger.info(f"{items_with_specific_qty} items with specific quantity")
            if items_with_general_qty > 0:
                logger.info(f"{items_with_general_qty} items with general quantity")
            
            # 
            # Phase 2c+6+6b: PL association, extraction, override, propagation
            # 
            logger.debug(f"DEBUG: Before PL associated_item update - subfolder_results={len(subfolder_results) if subfolder_results else 0}, file_classifications={len(file_classifications) if file_classifications else 0}")
            update_pl_associations(subfolder_results, file_classifications)

            logger.debug(f"DEBUG: After PL associated_item update, about to start Stage 6")
            pl_items_list, folder_stage6_tokens_in, folder_stage6_tokens_out = extract_and_process_pl(
                file_classifications, subfolder_results, client, email_data,
            )
            propagate_pl_data(subfolder_results, pl_items_list)

            # ═══════════════════════════════════════════════════════
            # STAGE 9: Smart Description Merge (o4-mini)
            # ═══════════════════════════════════════════════════════
            enable_stage9 = bool(selected_stages.get(9, True)) if selected_stages else True
            if enable_stage9 and subfolder_results and client:
                logger.info(f"[STAGE9] Stage 9: Smart merge descriptions ({len(subfolder_results)} items)...")
                try:
                    merged_count, s9_tok_in, s9_tok_out = _merge_descriptions(subfolder_results, client)
                    s9_cost = _calculate_stage_cost(s9_tok_in, s9_tok_out, STAGE_DESCRIPTION_MERGE)
                    cost_tracker.add_usage(s9_tok_in, s9_tok_out, cost=s9_cost)
                    logger.info(f"[STAGE9] Merged {merged_count} items (${s9_cost:.4f})")
                except Exception as s9_err:
                    logger.warning(f"[STAGE9] Failed: {s9_err}")
            elif not enable_stage9:
                logger.info("[STAGE9] Stage 9 disabled — skipping description merge")

            #  שמור קבצים בתוך התיקייה ואיסוף סטטיסטיקות
            folder_info, subfolder_results = save_folder_output(
                target_folder, subfolder_results, file_classifications, pl_items_list,
                confidence_level, timestamp,
                folder_classification_cost=folder_classification_cost,
                folder_extraction_cost_accurate=folder_extraction_cost_accurate,
                folder_extraction_tokens_in=folder_extraction_tokens_in,
                folder_extraction_tokens_out=folder_extraction_tokens_out,
                folder_stage6_tokens_in=folder_stage6_tokens_in,
                folder_stage6_tokens_out=folder_stage6_tokens_out,
                folder_start_time=folder_start_time,
            )
            if folder_info:
                folder_stats.append(folder_info)
            if subfolder_results:
                if file_classifications:
                    all_classifications.extend([fc for fc in file_classifications if fc and isinstance(fc, dict)])
                all_results.extend(subfolder_results)
                if file_classifications:
                    folder_classifications_map[target_folder] = [fc for fc in file_classifications if fc and isinstance(fc, dict)]
                else:
                    folder_classifications_map[target_folder] = []
        
        # All results processed with quantities
        if subfolder_results:
            logger.info(f"Folder '{target_folder.name}' finished - {len(subfolder_results)} drawings")
        else:
            logger.info(f"Folder '{target_folder.name}' - no drawings")
        
        # Add folder Stage 6 costs to global tracking
        global_stage6_tokens_in += folder_stage6_tokens_in
        global_stage6_tokens_out += folder_stage6_tokens_out
    
    except KeyboardInterrupt:
        # User pressed Q (Quit)
        logger.info("Stopped by user...")
        logger.info("All results so far were already saved in subfolders")
    
    # Copy all folders to TO_SEND AFTER all processing is complete
    if tosend_folder:
        copy_folders_to_tosend(
            subfolders_to_process, tosend_folder,
            folder_classifications_map, confidence_level, all_results,
        )
    
    # Merge all per-folder files into SUMMARY files in NEW FILES
    final_results_path, final_classification_path, all_file_classifications = merge_all_results(
        subfolders_to_process, output_folder, timestamp,
        all_results, all_classifications,
        global_classification_tokens_in=global_classification_tokens_in,
        global_classification_tokens_out=global_classification_tokens_out,
    )
    
    # Calculate execution time and cost summary
    end_time = time.time()
    execution_time = end_time - start_time
    
    try:
        cost_tracker.print_summary()
        logger.info(f"{ocr_engine.get_cache_stats()}")
        cost_summary = cost_tracker.get_summary()
    except Exception as e:
        logger.warning(f"Warning: Could not print cost summary: {e}")
        cost_summary = {
            'total_files': cost_tracker.total_files,
            'successful_files': cost_tracker.successful_files,
            'total_cost': 0,
            'execution_time': execution_time,
            'avg_time_per_drawing': 0
        }
    
    cost_summary['execution_time'] = execution_time
    cost_summary['avg_time_per_drawing'] = execution_time / cost_summary['successful_files'] if cost_summary['successful_files'] > 0 else 0
    
    # Add classification costs to summary
    cost_summary['classification_input_tokens'] = global_classification_tokens_in
    cost_summary['classification_output_tokens'] = global_classification_tokens_out
    cost_summary['classification_cost'] = _calculate_stage_cost(
        global_classification_tokens_in,
        global_classification_tokens_out,
        STAGE_CLASSIFICATION,
    )
    cost_summary['total_cost_with_classification'] = cost_summary['total_cost'] + cost_summary['classification_cost']
    
    # Add Stage 6 (PL extraction) costs to summary
    cost_summary['stage6_input_tokens'] = global_stage6_tokens_in
    cost_summary['stage6_output_tokens'] = global_stage6_tokens_out
    cost_summary['stage6_cost'] = _calculate_stage_cost(
        global_stage6_tokens_in,
        global_stage6_tokens_out,
        STAGE_PL,
    )
    cost_summary['total_cost_all'] = cost_summary['total_cost'] + cost_summary['classification_cost'] + cost_summary['stage6_cost']
    
    cost_summary['classification_time'] = global_classification_time
    cost_summary['classification_folder_count'] = classification_folder_count
    cost_summary['avg_classification_time_per_folder'] = global_classification_time / classification_folder_count if classification_folder_count > 0 else 0
    cost_summary['folder_stats'] = folder_stats
    
    print_final_summary(
        all_results, all_classifications,
        final_results_path, final_classification_path,
        output_folder, timestamp, cost_summary,
        subfolders_to_process, skipped_large_files, total_rafael_rows,
    )
    
    set_prompts_context(None)
    return all_results, output_folder, final_results_path, cost_summary, all_file_classifications


# Alias for GUI compatibility
scan_folder_with_stages = scan_folder


def main(folder: Optional[str] = None) -> None:
    """Main function"""
    logger.info("" + "="*70)
    logger.info("Customer Extractor V3.1 - File Classification + QUAD-STAGE")
    logger.info("="*70)
    logger.info("Features:")
    logger.info("Phase 0: Automatic file type classification")
    logger.info("Phase 1-4: Drawing processing (4 stages)")
    logger.info("Cost tracking & detailed reports")
    logger.warning(f"File size limits: Warn at {WARN_FILE_SIZE_MB}MB, Skip at {MAX_FILE_SIZE_MB}MB")
    logger.info("="*70)
    
    if folder is None:
        logger.info("Folder path:")
        folder = input("> ").strip()
        if not folder:
            folder = "."
    
    folder_path = Path(folder)
    
    # אם הטרמינל אינו אינטראקטיבי (לדוגמה בשילוב צינור/פייפ), דלג על הקלט
    import os, sys as _sys
    skip_date_prompt = os.environ.get("AI_DRAW_SKIP_DATE", "").lower() in {"1", "true", "yes"} or not _sys.stdin.isatty()
    if skip_date_prompt:
        date_input = ""
    else:
        logger.info("Filter by date? (DD/MM/YYYY or Enter to skip)")
        date_input = input("> ").strip()
    
    after_date = None
    if date_input:
        try:
            after_date = datetime.strptime(date_input, "%d/%m/%Y")
            logger.info(f"From {after_date.strftime('%d/%m/%Y')} onwards\n")
        except ValueError:
            logger.info("Invalid format. Processing all.\n")
    
    result = scan_folder(folder_path, recursive=True, after_date=after_date)
    
    if not result:
        logger.info("No results")
        return
    
    if isinstance(result, tuple) and len(result) == 5:
        results, project_folder, output_path, cost_summary, _all_file_classifications = result
    else:
        results, project_folder, output_path, cost_summary = result


if __name__ == "__main__":
    import sys
    folder = sys.argv[1] if len(sys.argv) > 1 else None
    main(folder)
