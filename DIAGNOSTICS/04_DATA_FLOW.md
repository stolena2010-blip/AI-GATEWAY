# AI GATEWAY KITARON — Data Flow

> עדכון אחרון: 03/04/2026 — **Multi-Profile Engine + Pipeline Decomposition + Profile-Aware Routing**

## 📊 זרימת נתונים כללית

```
  Email Inbox (Graph API / EWS)
       │
       ▼
  automation_runner.py
       │  _normalize_profile_config() → flat config with ai_engine_type, prompts_folder
       │  _run_once_internal_locked() → route by ai_engine_type
       │     ├─ "vision" → _scan_folder_compat(profile_config=config)
       │     └─ "document_intelligence" → skip (not yet implemented)
       │
       ▼
  _scan_folder_compat() → scan_folder(profile_config=config)
       │
       ▼
  customer_extractor_v3_dual.py :: scan_folder()
       │  set_prompts_context(profile_config.prompts_folder) ← thread-local
       │
       ├─→ archive_extractor.extract_archives_in_folders()
       ├─→ classify_file_type() ──→ DRAWING / PO / QUOTE / PL / ...
       │
       ├─→ drawing_processor.process_drawings()
       │        └─→ extract_drawing_data() ──→ Pipeline (Stages 0-4)
       │              ├─→ Stage 0: Layout (load_prompt uses prompts_folder context)
       │              ├─→ Stage 0.5: Rotation
       │              ├─→ Stage 1: Basic Info (P.N., customer)
       │              ├─→ Stage 2: Processes (material, coating, BOM)
       │              ├─→ Stage 3: Notes
       │              ├─→ Stage 4: Area
       │              ├─→ vote_best_pn() — 3-way voting
       │              ├─→ run_pn_sanity_checks() — checks A-D
       │              └─→ calculate_confidence() — full/high/medium/low/none
       │
       ├─→ pl_processor.{update,extract,propagate}_pl()
       ├─→ match_quantities_to_drawings()
       ├─→ override_pn_from_email()
       ├─→ merge_descriptions() — Stage 9 (o4-mini)
       │        └─→ lookup_color_prices() — BOM/COLORS.xlsx
       ├─→ validate_inserts_hardware()
       ├─→ enrich_inserts_with_prices() — BOM/INSERTS.xlsx
       │
       ├─→ folder_saver.save_folder_output()
       │        ├─→ _save_results_to_excel() ──→ Excel report
       │        ├─→ _save_text_summary() ──→ B2B text files
       │        └─→ _copy_folder_to_tosend() ──→ TO_SEND
       │
       └─→ results_merger.{merge,copy,print}_*()
              │
              ▼
       set_prompts_context(None)  ← reset thread context
       │
       ▼
  automation_runner.py  → send_email() → log entry → mark processed
```

---

## 📧 זרימת מייל (automation_runner.py) — per-profile

```
  PipelineBridge (singleton) ── 5× AutomationRunner threads
       │
       ├── quotes runner  → configs/quotes.json  → data/quotes/
       ├── orders runner  → configs/orders.json  → data/orders/
       ├── invoices runner→ configs/invoices.json→ data/invoices/
       ├── delivery runner→ configs/delivery.json→ data/delivery/
       └── complaints     → configs/complaints.json→ data/complaints/

  Per profile (each runner thread):
  1. list_messages(received_after, max_messages)
  2. Filter: skip_senders, skip_categories, processed IDs
  3. _count_drawing_files(message_dir)
       ├─→ ≤ max_files → process normally
       └─→ > max_files → mark "AI HEAVY", skip
  4. scan_folder(message_dir, config)
  5. _copy_folder_to_tosend() ─→ TO_SEND folder
       ├─ Rename files (B2BDraw_, B2BModel_, B2BImg_, B2BDoc_)
       ├─ Create ALL_METADATA.json + metadata.json
       ├─ B2B confidence filter (fallback if variant empty)
       └─ shutil.copytree → {tosend_folder}/{name}_TO_SEND
  6. Copy REPORT Excel → archive/{timestamp}/
  7. Send B2B email → recipient
  8. Log entry → data/{profile}/automation_log.jsonl
  9. Mark processed → data/{profile}/state.json
  10. Set category in Outlook
```

### Heavy Email Flow
```
  run_heavy() → _run_once_internal(heavy_only=True)
       → only processes messages with "AI HEAVY" category
       → no max_files_per_email limit
       → removes "AI HEAVY" category after processing
```

### RERUN Flow
```
  1. Detect RERUN (sender == mailbox = our own reply)
  2. Download reply with ALL_B2B attachment
  3. Remove old B2B-0_*, rename ALL_B2B → B2B-0_
  4. Swap ALL_METADATA → metadata.json
  5. Send files to recipient
  6. Copy to TO_SEND folder (shutil.copytree)
  7. Cleanup rerun_* folder from FROM
  8. Log entry with type: "RERUN"
```

---

## 📋 result_dict Schema

```python
{
    "filename": str,
    "file_type": "DRAWING" | "PURCHASE_ORDER" | "PARTS_LIST" | ...,
    "customer_name": str,
    "part_number": str,
    "drawing_number": str,
    "revision": str,
    "material": str,
    "surface_coating": str,
    "color_painting": str,
    "geometric_area": float | None,
    "dimensions_raw": str,
    "processes_list": list[str],
    "bom_items": list[dict],
    "notes_text": str,
    "quantity": int,
    "confidence_level": "full" | "high" | "medium" | "low" | "none",
    "merged_description": str,          # Stage 9 output
    "merged_specs": str,                # Stage 9 output
    "merged_highlights": str,           # Stage 9 output
    "color_price": float | None,        # from COLORS.xlsx
    "hardware_items": list[dict],       # from BOM + INSERTS.xlsx
    "stage_costs": dict,
    "total_cost_usd": float,
    "processing_time_seconds": float,
}
```

---

## 📊 automation_log.jsonl Entry Schema

```json
{
    "id": "auto_YYYYMMDDHHMMSS_sender",
    "timestamp": "2026-03-12T10:30:00Z",
    "received": "2026-03-12T10:25:00Z",
    "sender": "user@company.com",
    "customers": ["CUSTOMER_A"],
    "files_processed": 3,
    "items_count": 5,
    "accuracy_data": {
        "full": 3, "high": 1, "medium": 1, "low": 0, "none": 0, "total": 5
    },
    "cost_usd": 0.103,
    "processing_time_seconds": 262,
    "sent": true,
    "pl_overrides": 1,
    "error_types": [],
    "human_verified": false
}
```

---

## 🖥️ ★ Streamlit Data Flows

### Automation Page — Data Flow
```
  Browser
    │
    ▼
  session_state: runner, is_running, status_msg, log_lines, confirm_reset
    │
    ├─→ config_manager.load_config() ──→ automation_config.json ──→ form fields
    │
    ├─→ _header_status_fragment() [every 5s]
    │     ├─→ runner.get_run_status() ──→ status bar
    │     ├─→ detect_active_run() ──→ heavy status
    │     └─→ load_log_entries() → filter_by_period("today") ──→ cost display
    │
    ├─→ _live_log_fragment() [every 5s]
    │     └─→ read_log_tail() ──→ status_log.txt ──→ HTML container
    │
    ├─→ Save button ──→ _gather_config() ──→ save_config()
    ├─→ Run Once ──→ runner.run_once() (thread) ──→ st.status() progress
    ├─→ Run Heavy ──→ runner.run_heavy() (thread) ──→ st.status() progress
    ├─→ Start/Stop ──→ runner.start()/stop()
    └─→ Reset ──→ confirm_reset → reset_state()
```

### Dashboard Page — Data Flow
```
  load_log_entries() ──→ all JSONL files (deduplicated)
    │
    ├─→ filter_by_period(entries, period) ──→ email_entries
    │
    ├─→ KPI Cards (10):
    │     ├─→ _total_items/cost/time() ──→ current values
    │     └─→ _prev_period_entries() ──→ delta comparison
    │
    ├─→ Tab: Accuracy
    │     ├─→ _confidence_totals() ──→ distribution bar
    │     ├─→ _global_accuracy() / _email_accuracy() ──→ period grid
    │     ├─→ _entries_by_day() ──→ Plotly 14-day trend
    │     └─→ Weights Editor ──→ .env file (ACCURACY_WEIGHT_*)
    │
    ├─→ Tab: Efficiency
    │     └─→ statistics + Plotly distribution + daily breakdown
    │
    ├─→ Tab: Customers/Senders
    │     └─→ Top 10 tables + Plotly charts
    │
    ├─→ Tab: Recent Emails
    │     └─→ st.data_editor ──→ ✓ verification ──→ save_entry_field() ──→ JSONL
    │
    └─→ Tab: Export
          ├─→ openpyxl ──→ Excel (5 sheets) ──→ st.download_button
          └─→ Reset Stats ──→ confirm → backup + clear JSONL
```

### Accuracy Weights Flow
```
  .env file
    │ ACCURACY_WEIGHT_FULL=1.0
    │ ACCURACY_WEIGHT_HIGH=1.0
    │ ACCURACY_WEIGHT_MEDIUM=0.8
    │ ACCURACY_WEIGHT_LOW=0.5
    │ ACCURACY_WEIGHT_NONE=0.0
    │
    ├─→ get_accuracy_weights() ──→ os.getenv()
    │     └─→ calc_weighted_accuracy() ──→ per-entry score
    │
    └─→ Dashboard Weights Editor
          └─→ Save ──→ write .env + os.environ update ──→ st.rerun()
```

### Human Verification Flow
```
  Dashboard "Recent Emails" tab
    │
    ├─→ Load entries[:100] ──→ pd.DataFrame
    ├─→ st.data_editor (checkbox column "✓ אימות")
    └─→ On change ──→ save_entry_field(entry_id, "human_verified", bool)
                        └─→ Rewrite JSONL line in-place
```

---

## 🔄 OCR Fallback Chain

```
  Stage 1 extract_basic_info
    │
    ├─→ Vision API (full image + title block)
    │     └─→ Success? → done
    │
    ├─→ MultiOCREngine
    │     ├─→ pytesseract (Hebrew + English)
    │     ├─→ Azure Vision API OCR
    │     └─→ combined + deduplicated
    │
    └─→ extract_stage1_with_retry (higher DPI, bigger crop)
```

---

## 📄 Excel Output Sheets

| Sheet | Content |
|-------|---------|
| תוצאות | Main results per drawing |
| סיווג קבצים | File classification report |
| Parts List | PL items + associated drawings |
| BOM | Hardware + insert prices |
| סיכום | Summary statistics |

---

## 📤 B2B Output Format

```
Field 1:  מק"ט (P.N.)
Field 2:  גרסה (Revision)
Field 3:  שם לקוח
Field 4:  כמות
Field 5:  חומר
Field 6:  שטח (m²)
Field 7:  ציפוי פנים
Field 8:  צביעה חיצונית
Field 9:  מחיר צבע
Field 10: הערות
Field 11: merged_description (תיאור מורחב — Stage 9)
```
