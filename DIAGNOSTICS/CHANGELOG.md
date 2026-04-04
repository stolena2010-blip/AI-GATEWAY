# Changelog

כל השינויים המשמעותיים בפרויקט מתועדים כאן.

## [4.1.0] - 2026-04-04

### חדש — Pipeline Decomposition
- **פיצול scan_folder()**: מ-1,816 שורות ל-650 שורות — 5 מודולי pipeline חדשים ב-`src/pipeline/`:
  - `archive_extractor.py` (121 שורות) — חילוץ ופתיחת ארכיונים
  - `drawing_processor.py` (202 שורות) — עיבוד שרטוטים (Vision API)
  - `pl_processor.py` (404 שורות) — עיבוד Parts List
  - `folder_saver.py` (290 שורות) — שמירת תוצרים לתיקיות
  - `results_merger.py` (334 שורות) — מיזוג תוצאות ויצוא Excel/B2B
- **customer_extractor_v3_dual.py**: צומצם מ-2,127 ל-987 שורות

### חדש — Profile-Aware Infrastructure
- **prompt_loader.py** (57 שורות, היה 39):
  - `set_prompts_context(prompts_folder)` — thread-local context לטעינת prompts לפי פרופיל
  - `load_prompt()` בודק: explicit arg → thread context → root prompts/ fallback
  - הוסר `@lru_cache` (לא תואם folders דינמיים)
- **scan_folder()** — פרמטר חדש `profile_config: Dict = None`; מגדיר prompts context בכניסה ומאפס ביציאה
- **automation_runner.py** — `_normalize_profile_config()` שומר `ai_engine_type`, `prompts_folder`, `profile_name`; `_scan_folder_compat()` מעביר `profile_config`; ניתוב לפי `ai_engine_type` (vision → scan_folder, document_intelligence → skip עם warning)
- **automation_panel_gui.py** — dropdown לבחירת פרופיל; `_discover_profiles()` סורק `configs/*.json`; `_on_profile_changed()` טוען config → normalize → שמירה → recreate runner

### תיקונים — Dashboard Profile Separation
- **log_reader.py** — `load_all_profile_log_entries()` היה תמיד טוען quotes; תוקן להעביר profile_name ל-`load_log_entries()`
- **log_reader.py** — fallback ללוגים ב-root מוגבל עכשיו רק ל-`profile_name == "quotes"`
- תוצאה: quotes=1,969 רשומות, שאר הפרופילים=0 (נכון)

### סטטיסטיקות
- 430 טסטים עוברים (3 skipped, 2 warnings)
- `src/pipeline/` — 1,351 שורות סה"כ (5 מודולים)
- `prompts/quotes/` — 15 prompts (זהים ל-root)

---

## [4.0.0] - 2026-04-03

### חדש — Multi-Profile Engine
- **שינוי שם**: DrawingAI Pro → **AI GATEWAY KITARON**
- **5 פרופילי מסמכים**: quotes (הצעות), orders (הזמנות), invoices (חשבוניות), delivery (תעודות משלוח), complaints (תלונות)
- **configs/{profile}.json** — קונפיג עצמאי לכל פרופיל (תיבות, תיקיות, תזמון, שלבים, מודלים)
- **data/{profile}/** — state, logs, health, alert נפרדים לכל פרופיל
- **PipelineBridge** — singleton ל-5 runners עם scheduler threads נפרדים
- **RunnerBridge** — backward compat ל-quotes

### חדש — UI פר-פרופיל
- **טאבים צבעוניים** לפי פרופיל (quotes=כחול, orders=כתום, invoices=ירוק, delivery=סגול, complaints=אדום)
- **Profile banners** — header צבעוני עם אייקון בכל טאב
- **`profile_tab_css()`** + **`profile_banner()`** ב-brand.py
- כל הדפים (Automation, Dashboard, Email) עודכנו עם banners + colored tabs
- **Dashboard per-profile** — טאב נפרד לכל פרופיל + טאב "סה"כ" משולב

### תיקונים — Multi-Profile Safety
- **Scheduler race condition** — `start_scheduler()` ב-RunnerBridge + PipelineBridge עטוף ב-`with self._lock`
- **stdout redirect** — הוחלף global `_STATUS_LOG_PATH` ב-thread-aware `_thread_log_paths` dict + `_active_count`
- **Logger prefix** — `_ProfileFilter` מזריק `quotes:automation_runner` format לכל ה-handlers
- **B2B confidence fallback** — כשאין שורות HIGH, שומר B2B מקורי במקום למחוק (file_utils.py)
- **RERUN TO_SEND** — `_handle_rerun()` מעתיק עכשיו ל-TO_SEND folder (היה חסר `shutil.copytree`)
- **RERUN cleanup** — `_scan_rerun_folder()` מנקה `rerun_*` folders מ-from/ (449 תיקיות הצטברו)

### תיקונים — נתיבים
- תיקון 5 נתיבים מ-`C:\DrawingAI` ל-`C:\dev DrawingAI` ב-automation_config.json + export_hardware_history_excel.py

## [3.2.1] - 2026-03-26

### ניסוי סנכרון
- בדיקת זרימת עבודה: שינוי ב-DEV -> push ל-Repo -> pull לשרת אמת.

## [3.2.0] - 2026-03-25

### חדש
- **Streamlit Web UI** — ממשק Web מלא (3 עמודים: Automation, Dashboard, Email)
- **Dashboard** — 10 KPI cards עם delta, 6 tabs, Plotly charts, human verification
- **Automation Page** — 4 tabs, live log, progress indicator, reset confirmation
- **Scheduler Report** — דוח Excel אוטומטי (schedule_report_latest.xlsx) בסוף כל סבב
- **Report Exporter** — backend module לייצוא דוחות מתוזמנים
- **Runner Bridge** — thread-safe wrapper ל-AutomationRunner בסביבת Streamlit
- **Brand Module** — CSS, לוגו, RTL, dark theme (#FF8C00)
- **Weights Editor** — עריכת משקלות דיוק מהדשבורד (שמירה ל-.env)
- **Stage 9 Merge** — מיזוג תיאורים חכם באמצעות o4-mini
- **Color/Insert Price Lookup** — חיפוש מחירי צבע וקשיחים מקטלוג BOM
- **Insert Validator** — אימות קשיחים
- **Quantity Matcher** — חילוץ כמויות ממיילים ומזמינות רכש
- **P.N. Voting** — pdfplumber + Tesseract + Vision voting
- **Sanity Checks** — בדיקות תקינות מתקדמות
- **deploy/** — סקריפטי התקנה (install_server.ps1, register_service.ps1, UPDATE.bat)

### שיפורים
- הוספת 20 קבצי בדיקות (סה"כ 25)
- requirements.lock לנעילת תלויות
- ניקוי קבצים שלא בשימוש (TEMP/, גיבויים, סקריפטים חד-פעמיים)
- עדכון תיעוד ו-MANIFEST

## [3.1.0] - 2026-02-21

### תיקונים
- **PL Detection** — regex לא תפס `PL_TL-4341` (underscore = word char). תיקון: lookahead/lookbehind
- **Text-Heavy Threshold** — סף 2000 מילים חסם שרטוטים עם routing chart. שונה ל-700 מילים/עמוד
- **Text-Heavy V3** — keyword bypass (DRAWING NO, P.N., SCALE → skip check)
- **PO DPI** — 400 DPI × zoom ×3 = 135MP = 3.5 שעות. הופחת ל-200 DPI × zoom ×2 = 11MP = 30 שניות
- **Smart DPI** — שרטוטים ענקיים (>12K px) לא עוברים upscale ל-400 DPI
- **Stop Button** — `_stop_event` לא נבדק בלולאת המיילים. הוספת check בתחילת כל מייל
- **State Save** — באג: per-message save כתב dict ריק. תוקן + logging + fallback
- **Exception Logging** — outer try/except שינה מ-debug ל-error + full traceback

### חדש
- **Dashboard: Items per Mail** — סקציה חדשה עם ממוצע, חציון, התפלגות
- **Dashboard: Reset with Time** — שדה שעה:דקה באיפוס סטטיסטיקה
- **Smart P.N. Voting** — pdfplumber + Tesseract + Vision voting

## [3.0.0] - 2026-02-01

### חדש
- Automation Runner — ניטור אוטומטי של Shared Mailbox
- 5 GUI Panels — Automation, Extractor, Dashboard, Email, Send
- Parts List integration — PL parsing + association
- 3 customer models — Rafael, IAI, Generic
- Confidence system — FULL/HIGH/MEDIUM/LOW
- B2B variants — 3 versions filtered by confidence

## [2.0.0] - 2025-12-01

### חדש
- Multi-stage pipeline (9 stages)
- Azure OpenAI GPT-4o integration
- Microsoft Graph API (replacing EWS)
- OCR engine with Tesseract + pdfplumber
- Disambiguation engine (O↔0, B↔8)
