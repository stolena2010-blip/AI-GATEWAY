# AI GATEWAY KITARON — סקירת פרויקט

> עדכון אחרון: 03/04/2026 — **Multi-Profile Engine (v4.1) — Pipeline Decomposition + Profile-Aware Infrastructure**

## 📌 תיאור כללי

**AI GATEWAY KITARON** (לשעבר DrawingAI Pro) הוא מערכת Multi-Profile לניתוח אוטומטי של מסמכים הנדסיים
באמצעות Azure OpenAI Vision API.
המערכת תומכת ב-5 פרופילים עצמאיים:
- **quotes** — הצעות מחיר (📐) — פעיל מלא
- **orders** — הזמנות (📦)
- **invoices** — חשבוניות (🧾)
- **delivery** — תעודות משלוח (📋)
- **complaints** — תלונות (📣)

כל פרופיל פועל עם קונפיג עצמאי (`configs/{profile}.json`), מתזמן נפרד,
tabs צבעוניים ב-UI, ותיקיית state/logs נפרדת (`data/{profile}/`).

### נקודות כניסה

| קובץ | תפקיד | שורות |
|-------|--------|------:|
| `Run_Web.bat` | מפעיל Streamlit Web UI | — |
| `Run_GUI.bat` | מפעיל את ה-GUI הראשי (Tkinter Legacy) | — |
| `streamlit_app/app.py` | ★ Streamlit entry point — ממשק Web ראשי | 42 |
| `customer_extractor_gui.py` | ממשק גרפי (Tkinter Legacy) | 1,303 |
| `customer_extractor_v3_dual.py` | מנוע הליבה (pipeline) | 987 |
| `main.py` | נקודת כניסה CLI | 50 |
| `automation_runner.py` | הרצה אוטומטית מחזורית + heavy + RERUN | 2,038 |
| `automation_main.py` | Tkinter entry point | 66 |

---

## 🏗️ ארכיטקטורה — מבנה תקיות

```
AI GATEWAY KITARON/
├── customer_extractor_v3_dual.py    ← מנוע ליבה (pipeline ראשי) — 987 שורות
├── customer_extractor_gui.py        ← GUI ראשי (Tkinter Legacy) — 1,303 שורות
├── automation_runner.py             ← runner אוטומטי + heavy + RERUN — 2,038 שורות
├── process_analysis.py              ← סטטיסטיקות תהליכים/חומרים — 403 שורות
├── main.py                          ← CLI entry point — 50 שורות
├── automation_main.py               ← Tkinter entry point — 66 שורות
│
├── configs/                         ← ★ קונפיג פר-פרופיל
│   ├── quotes.json                  ← הצעות מחיר (פעיל מלא)
│   ├── orders.json                  ← הזמנות
│   ├── invoices.json                ← חשבוניות
│   ├── delivery.json                ← תעודות משלוח
│   └── complaints.json              ← תלונות
│
├── data/                            ← ★ state/logs פר-פרופיל
│   ├── quotes/                      ← state.json, status_log.txt, automation_log.jsonl
│   ├── orders/
│   ├── invoices/
│   ├── delivery/
│   └── complaints/
│
├── streamlit_app/                   ← ★ Streamlit Web UI — per-profile tabs
│   ├── app.py                       ← 42 שורות — entry point + page config
│   ├── brand.py                     ← CSS, לוגו, brand, **profile colors & banners**
│   ├── backend/
│   │   ├── config_manager.py        ← R/W configs/{profile}.json + load_all_profiles()
│   │   ├── email_helpers.py         ← חיבור תיבות משותפות + folders
│   │   ├── excel_report_builder.py  ← Excel report generation (dashboard export)
│   │   ├── log_reader.py            ← JSONL log + live log + detection
│   │   ├── report_exporter.py       ← report export helper
│   │   ├── runner_bridge.py         ← thread-safe wrapper (quotes backward compat)
│   │   └── pipeline_bridge.py       ← ★ PipelineBridge singleton — 5 runners + per-profile scheduler
│   ├── components/
│   └── pages/
│       ├── 1_🚀_Automation.py       ← פאנל אוטומציה פר-פרופיל (colored tabs + banner)
│       ├── 2_📊_Dashboard.py        ← דשבורד סטטיסטיקה פר-פרופיל + טאב "סה"כ"
│       └── 3_📧_Email.py            ← ניהול מייל פר-פרופיל
│
├── src/                             ← מודולים מחולצים — 14,495 שורות
│   ├── core/                        ← קבועים, הגדרות, exceptions
│   │   ├── constants.py             ← 90 שורות — קבועים משותפים (HUB)
│   │   ├── config.py                ← 181 שורות — Config classes
│   │   ├── cost_tracker.py          ← 78 שורות — מעקב עלויות
│   │   └── exceptions.py            ← 65 שורות — exception hierarchy
│   │
│   ├── services/
│   │   ├── ai/
│   │   │   ├── model_runtime.py     ← 254 שורות — ModelRuntimeConfig + endpoint helpers
│   │   │   └── vision_api.py        ← 279 שורות — Vision API + GPT-4o fallback
│   │   ├── image/
│   │   │   └── processing.py        ← 812 שורות — סיבוב, downsample, quality
│   │   ├── extraction/              ← חילוץ מידע — 16 מודולים
│   │   │   ├── stages_generic.py    ← 437 שורות
│   │   │   ├── stages_rafael.py     ← 314 שורות
│   │   │   ├── stages_iai.py        ← 310 שורות
│   │   │   ├── stage9_merge.py      ← 373 שורות — Stage 9: o4-mini merge
│   │   │   ├── color_price_lookup.py← 324 שורות
│   │   │   ├── insert_price_lookup.py←172 שורות
│   │   │   ├── insert_validator.py  ← 133 שורות
│   │   │   ├── ocr_engine.py        ← 554 שורות
│   │   │   ├── filename_utils.py    ← 594 שורות
│   │   │   ├── document_reader.py   ← 783 שורות
│   │   │   ├── drawing_pipeline.py  ← 775 שורות
│   │   │   ├── pn_voting.py         ← 238 שורות
│   │   │   ├── sanity_checks.py     ← 555 שורות
│   │   │   ├── post_processing.py   ← 135 שורות
│   │   │   └── quantity_matcher.py  ← 399 שורות
│   │   ├── file/
│   │   │   ├── file_utils.py        ← 708 שורות
│   │   │   ├── classifier.py        ← 339 שורות
│   │   │   └── file_renamer.py      ← 89 שורות
│   │   ├── reporting/
│   │   │   ├── b2b_export.py        ← 258 שורות
│   │   │   ├── pl_generator.py      ← 942 שורות
│   │   │   └── excel_export.py      ← 610 שורות
│   │   └── email/
│   │       ├── shared_mailbox.py    ← 593 שורות — EWS
│   │       ├── graph_mailbox.py     ← 916 שורות — Graph API
│   │       ├── graph_helper.py      ← 528 שורות
│   │       ├── graph_auth.py        ← 261 שורות
│   │       └── factory.py           ← 168 שורות
│   ├── pipeline/                    ← ★ מודולי pipeline מחולצים מ-scan_folder
│   │   ├── archive_extractor.py     ← 121 שורות — חילוץ ארכיונים
│   │   ├── drawing_processor.py     ← 202 שורות — עיבוד שרטוטים
│   │   ├── pl_processor.py          ← 404 שורות — עיבוד Parts List
│   │   ├── folder_saver.py          ← 290 שורות — שמירת תוצרים + TO_SEND
│   │   └── results_merger.py        ← 334 שורות — מיזוג תוצאות + דוחות
│   ├── models/
│   │   ├── drawing.py               ← 180 שורות
│   │   └── enums.py                 ← 48 שורות
│   └── utils/
│       ├── logger.py                ← 141 שורות
│       └── prompt_loader.py         ← 57 שורות — ★ profile-aware (thread-local context)
│
├── prompts/                         ← 15 פרומפטים ל-AI + תת-תיקיות פר-פרופיל
│   ├── *.txt                        ← 15 פרומפטים (root fallback)
│   ├── quotes/                      ← 15 פרומפטים (זהים ל-root)
│   ├── orders/                      ← ריק (ממתין לתוכן)
│   ├── invoices/                    ← ריק (ממתין לתוכן)
│   ├── delivery/                    ← ריק (ממתין לתוכן)
│   └── complaints/                  ← ריק (ממתין לתוכן)
├── tests/                           ← 25 קבצי בדיקות (430 tests)
├── BOM/                             ← COLORS.xlsx, INSERTS.xlsx
├── deploy/                          ← install_server.ps1, register_service.ps1, UPDATE.bat
├── .streamlit/                      ← config.toml (theme, server, client)
└── logs/                            ← קבצי לוג
```

---

## 📊 סיכום שורות קוד

| תחום | ערך |
|-------|──────:|
| **סה"כ Python files** | **102** |
| פרומפטים AI | 15 קבצים |
| בדיקות | 25 קבצים |

---

## 🖥️ ★ Streamlit Web UI — ארכיטקטורה

### מבנה שכבות

```
┌──────────────────────────────────┐
│  Browser (localhost:8501)         │
├──────────────────┬───────────────┤
│  Pages (per-profile) │  Brand/CSS    │
│  🚀 Automation       │  brand.py     │
│  📊 Dashboard        │  (RTL, dark,  │
│  📧 Email            │  profile      │
│  📝 Review           │  colors+      │
│                      │  banners)     │
├──────────────────┴───────────────┤
│  Backend Layer                    │
│  config_manager │ pipeline_bridge │
│  log_reader     │ runner_bridge   │
│  email_helpers  │                 │
├──────────────────────────────────┤
│  Core Engine (per-profile runner)  │
│  automation_runner.py              │
│  customer_extractor_v3_dual.py     │
└──────────────────────────────────┘
```

### Profile Colors
| Profile | צבע | Icon | Accent |
|---------|------|------|--------|
| quotes | כחול | 📐 | #3b82f6 |
| orders | כתום | 📦 | #f59e0b |
| invoices | ירוק | 🧾 | #10b981 |
| delivery | סגול | 📋 | #8b5cf6 |
| complaints | אדום | 📣 | #ef4444 |

### 🚀 Automation Page (פר-פרופיל)
- **Header**: auto-refresh `@st.fragment(run_every=5)` — סטטוס רגיל + כבדים + עלות יומית
- **7 כפתורים**: שמור, בדוק, Run Once, Run Heavy, התחל, עצור, Reset (confirmation)
- **4 tabs**: Email+Folders, Stages+Models, Run Settings, Live Log
- **tooltips** (help=) על כל שדה
- **Progress indicator** (`st.status`) בזמן ריצה
- **Reset confirmation**: דו-שלבי — לחיצה ראשונה מזהירה, שנייה מאשרת
- **Live Log**: @st.fragment(run_every=5), status bar, HTML container

### 📊 Dashboard Page (936 שורות)
- **Period filter**: היום/שבוע/חודש/הכל/טווח מותאם
- **10 KPI cards** בשתי שורות עם delta indicators:
  - Row 1: תקופה → מיילים → שורות → דיוק מיילים → דיוק שורות
  - Row 2: זמן/מייל → זמן/שורה → עלות/מייל → עלות/שורה → עלות כוללת
- **6 tabs**: דיוק, יעילות, לקוחות, שולחים, הודעות אחרונות, ייצוא
- **Weights editor**: expander לעריכת משקלות דיוק (שמירה ל-.env)
- **Human verification**: `st.data_editor` עם עמודת ✓ אימות (שמירה ל-JSONL)
- **Plotly charts**: 14-day accuracy trend, daily cost breakdown, distribution bars
- **Excel export**: 5 sheets (סיכום, מיילים, יומי, לקוחות, שולחים)

### תצורה (.streamlit/config.toml)
```toml
[theme]       # dark, orange primary (#FF8C00)
[server]      # headless, port 8501, 0.0.0.0
[browser]     # gatherUsageStats = false
[client]      # toolbarMode = "minimal"
```

---

## ⚙️ Pipeline — תהליך עיבוד

### Pipeline לכל שרטוט (`extract_drawing_data`):

| # | שלב | מודול | פרומפט |
|---|------|-------|--------|
| 0 | Layout | `stages_generic` | `01_identify_drawing_layout.txt` |
| 0.5 | Rotation | `processing` | `10_detect_rotation.txt` |
| 1 | Basic Info | `stages_generic` | `02_extract_basic_info.txt` |
| 2 | Processes | `stages_generic` | `03_extract_processes.txt` |
| 3 | Notes | `stages_generic` | `04_extract_notes_text.txt` |
| 4 | Area | `stages_generic` | `05_calculate_geometric_area.txt` |
| 5 | Fallback | `stages_rafael` | `06b_extract_processes_from_notes.txt` |
| 9 | Merge | `stage9_merge` | `09_merge_work_descriptions.txt` |

---

## 🔌 תלויות חיצוניות

| חבילה | שימוש |
|--------|-------|
| `openai` | Azure OpenAI Vision API |
| `streamlit` | Web UI framework |
| `plotly` | Dashboard charts |
| `pandas` | DataFrames + Excel export |
| `openpyxl` | Excel styling, BOM catalogs |
| `opencv-python` | Image processing, OCR preprocessing |
| `Pillow` | Image manipulation |
| `pdfplumber` | PDF reading |
| `pytesseract` | OCR (Tesseract) |
| `python-dotenv` | .env loading |
| `msal` | Microsoft Graph auth |

---

## 📝 קבצי הגדרות

| קובץ | תפקיד |
|-------|-------|
| `.env` | Azure OpenAI creds, model config, pricing, ACCURACY_WEIGHT_* |
| `automation_config.json` | הגדרות הרצה אוטומטית + heavy email |
| `automation_state.json` | processed IDs, next run time |
| `email_config.json` | הגדרות חיבור דואר |
| `.streamlit/config.toml` | Streamlit theme, server, client |
| `prompts/*.txt` | 15 פרומפטים AI |
| `BOM/COLORS.xlsx` | קטלוג צבעים |
| `BOM/INSERTS.xlsx` | קטלוג קשיחים |

---

## 📈 היסטוריה

| תאריך | שינוי |
|--------|-------|
| 21/03/2026 | עדכון ספירות שורות, הוספת קבצי backend חסרים, 2 קבצי טסטים חדשים (sanity_checks, drawing_pipeline) |
| 21/03/2026 | רענון תיעוד: עדכון תאריכים ותיאורי אבחון בתיקיית DIAGNOSTICS |
| 25/03/2026 | ניקוי קבצים שלא בשימוש (TEMP/, גיבויים, סקריפטים חד-פעמיים), עדכון כל התיעוד, MANIFEST ו-CHANGELOG |
| 01/03/2026 | ריפקטורינג: חילוץ 6 מודולים (4,018 → 2,059 שורות) |
| 03/2026 | Stage 9, Color/Insert lookups, Insert Validator |
| 07/03/2026 | B2B field 11 → merged_description |
| 09/03/2026 | Heavy Email + Process Analysis + Graph categories |
| 10-12/03/2026 | ★ Streamlit Web UI (3 pages, backend, brand, auto-refresh) |
| 12/03/2026 | 10 KPI + deltas, weights editor, human verification, tooltips, reset confirmation, progress, cost header, toolbarMode=minimal, GPT-4o fallback |
| 03/04/2026 | **v4.0** Multi-Profile Engine: 5 פרופילים, configs/, data/, PipelineBridge, colored tabs |
| 03/04/2026 | **v4.1** Pipeline Decomposition: scan_folder 1,816→650 שורות, 5 pipeline modules מחולצים |
| 03/04/2026 | **v4.1** Profile-Aware Infrastructure: prompt_loader thread-local, scan_folder profile_config, DI routing, GUI profile selector, Dashboard profile separation |
