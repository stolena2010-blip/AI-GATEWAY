# AI GATEWAY KITARON

**Multi-profile automated document processing powered by Azure OpenAI Vision API.**

## Overview

AI GATEWAY KITARON (formerly DrawingAI Pro) is a multi-profile automation engine for processing engineering documents received via email. It supports 5 document types — quotes, orders, invoices, delivery notes, and complaints — each with its own mailbox, scheduling, and processing pipeline. Files are processed through multi-stage AI analysis, classified, extracted, and exported as structured Excel and B2B reports.

## Key Features

- **Multi-profile engine**: 5 document types (quotes, orders, invoices, delivery, complaints), each with independent config, scheduler, and UI tab
- **Multi-stage extraction**: basic info, processes, notes, geometric area, merge, validation
- **Per-profile visual distinction**: colored tabs, profile banners, separate logs
- **Customer-specific logic** (IAI / RAFAEL / Generic variants)
- **File classification** (drawings vs documents)
- **B2B export** with confidence levels (LOW/MEDIUM/HIGH) and fallback safety
- **Automated email workflow**: receive → download → analyze → export → send
- **RERUN support**: user approval flow with ALL_B2B → B2B swap + TO_SEND copy
- **Multi-mailbox support** via Microsoft Graph API
- **Cost tracking** per Azure API stage
- **OCR** with Tesseract + advanced image preprocessing
- **Streamlit Web UI** — real-time dashboard, automation panel, email management (per-profile)
- **Concurrent safety**: thread-aware logging, per-profile stdout redirect, scheduler locks
- **Per-model Azure endpoints**: separate Azure resources per model via env vars
- **Pipeline decomposition**: scan_folder() פורק ל-5 מודולים ב-`src/pipeline/` (1,351 שורות סה"כ)
- **Profile-aware prompts**: `prompt_loader.py` תומך thread-local context לטעינת prompts לפי פרופיל (`prompts/{profile}/`)
- **DI engine routing**: automation_runner מנתב לפי `ai_engine_type` (vision / document_intelligence)

## Architecture

```
streamlit_app/                   — ★ Streamlit Web UI (per-profile tabs)
├── backend/                     — config_manager, runner_bridge, pipeline_bridge, log_reader
├── pages/                       — 4 Streamlit pages (Automation, Dashboard, Email, Review)
└── brand.py                     — CSS, logos, RTL, profile colors & banners

configs/                         — Per-profile JSON configs (quotes, orders, invoices, delivery, complaints)
data/{profile}/                  — Per-profile runtime state (state.json, status_log.txt, automation_log.jsonl)

customer_extractor_v3_dual.py    — Main orchestrator (scan_folder + extraction pipeline)
automation_runner.py             — Automated email processing cycle + RERUN + heavy email

src/
├── core/                        — Config, constants, cost tracker, exceptions
├── pipeline/                    — ★ 5 מודולי pipeline (פורקו מ-scan_folder):
│   ├── archive_extractor.py     — חילוץ ופתיחת ארכיונים (121 שורות)
│   ├── drawing_processor.py     — עיבוד שרטוטים Vision API (202 שורות)
│   ├── pl_processor.py          — עיבוד Parts List (404 שורות)
│   ├── folder_saver.py          — שמירת תוצרים לתיקיות (290 שורות)
│   └── results_merger.py        — מיזוג תוצאות ויצוא Excel/B2B (334 שורות)
├── services/
│   ├── ai/vision_api.py         — Azure OpenAI API calls with retry logic
│   ├── ai/model_runtime.py      — Per-model endpoint/key config
│   ├── image/processing.py      — Image preprocessing, rotation, OCR
│   ├── extraction/              — 16 modules: pipeline stages, OCR, P.N. voting, sanity checks
│   ├── file/                    — File classification, renaming, metadata, TO_SEND operations
│   ├── reporting/               — Excel reports, B2B export, PL generation
│   └── email/                   — Microsoft Graph API email integration
├── models/                      — Drawing models, enums
└── utils/                       — Logger (with per-profile filter), prompt loader (profile-aware)
```

## Quick Start

### Prerequisites

- Python 3.10+
- Tesseract OCR installed
- Azure OpenAI API access

### Installation

```bash
git clone <repo-url>
cd "AI DRAW_STEAMLIT"
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Azure OpenAI credentials
```

### Running

```bash
Run_Web.bat                 # Streamlit Web UI (recommended)
Run_GUI.bat                 # Legacy Tkinter GUI (Windows)
Run_Statistics.bat          # Process analysis statistics
python main.py              # CLI mode
```

### Running Tests

```bash
pytest
```

## Project Stats

| Metric | Value |
|--------|-------|
| Python files | ~105 |
| Prompt templates | 15 (×6 profile folders) |
| Pipeline modules | 5 (src/pipeline/) |
| Test files | 25 (430 tests) |
| Streamlit pages | 3 |

```bash
python -m pytest tests/ -v
```

## Configuration

All configuration is via `.env` file. See `.env.example` for available options.

## Project Stats

- 430 automated tests (25 test files)
- 5 pipeline modules + 16 extraction modules
- Multi-mailbox email automation
- 99.7% success rate in production (594 emails processed)
