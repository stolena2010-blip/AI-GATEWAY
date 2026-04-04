# AI GATEWAY KITARON - מסמך מערכת מלא

## 1) מטרת הפרויקט

AI GATEWAY KITARON (לשעבר DrawingAI Pro) היא מערכת Multi-Profile לניתוח אוטומטי של מסמכים הנדסיים ועסקיים מתיבות מייל משותפות.

המערכת תומכת ב-5 סוגי מסמכים (פרופילים):
- **quotes** — הצעות מחיר (הפרופיל המקורי, פעיל מלא)
- **orders** — הזמנות
- **invoices** — חשבוניות
- **delivery** — תעודות משלוח
- **complaints** — תלונות

המוצר משלב:
- OCR ושיפור תמונה
- Azure OpenAI Vision לחילוץ מידע מובנה
- תהליך רב-שלבי (מידע בסיסי, תהליכים, NOTES, שטח, Fallback)
- **Pipeline משותף עם Processor מתחלף** — תשתית אימייל/הורדה/שליחה משותפת, עיבוד ספציפי לפרופיל
- ממשק Streamlit Web UI עם טאבים צבעוניים לכל פרופיל
- יצוא תוצרים עסקיים (Excel, קבצי B2B, קבצים ממוספרים לשליחה)
- **בטיחות Multi-Profile**: logs נפרדים, scheduler locks, thread-aware stdout redirect

---

## 2) נקודות כניסה והרצה

- [Run_Web.bat](Run_Web.bat) - ★ ממשק Streamlit Web UI (מומלץ)
- [Run_GUI.bat](Run_GUI.bat) - ממשק Tkinter Legacy ב-Windows
- [Run_Statistics.bat](Run_Statistics.bat) - סטטיסטיקות תהליכים
- [customer_extractor_gui.py](customer_extractor_gui.py) - GUI ראשי למנוע הניתוח (Tkinter)
- [main.py](main.py) - נקודת כניסה CLI
- [customer_extractor_v3_dual.py](customer_extractor_v3_dual.py) - מנוע העיבוד המרכזי
- [streamlit_app/app.py](streamlit_app/app.py) - Streamlit entry point

---

## 3) ארכיטקטורה ברמת על

### שכבת UI — Streamlit Web (מומלץ)
- [streamlit_app/](streamlit_app/) — ★ ממשק Web ראשי
	- דשבורד בזמן אמת עם 10 KPI cards
	- פאנל אוטומציה מלא (4 tabs)
	- ניהול מייל
	- ייצוא דוח Excel בסוף כל סבב

### שכבת UI — Tkinter Legacy
- [customer_extractor_gui.py](customer_extractor_gui.py)
	- בחירת תיקייה, בחירת שלבים, אפשרויות OCR ורמת ביטחון B2B
	- שילוב פאנל מייל ופאנל אוטומציה
- [email_panel_gui.py](email_panel_gui.py)
	- בדיקת חיבור לתיבה, רענון תיקיות, הורדה מתיקייה נבחרת, שליחה ידנית
- [automation_panel_gui.py](automation_panel_gui.py) (1,374 שורות)
	- תזמון אוטומציה, הגדרת תיבות מרובות, בחירת תיקייה מהתיבה, תצוגת סטטוס
	- **dropdown לבחירת פרופיל** — `_discover_profiles()` + `_on_profile_changed()`

### שכבת לוגיקה עסקית
- [customer_extractor_v3_dual.py](customer_extractor_v3_dual.py) (987 שורות)
	- OCR + Vision + פוסט-פרוססינג + יצוא קבצים
	- `scan_folder()` (650 שורות) — מקבל `profile_config` ומגדיר prompts context לפי פרופיל
- [automation_runner.py](automation_runner.py) (2,038 שורות)
	- תהליך מחזורי: משיכת מיילים, הורדה, ניתוח, העברה ל-TO_SEND, שליחה וסימון
	- `_normalize_profile_config()` — ממיר nested ל-flat, שומר `ai_engine_type` + `prompts_folder` + `profile_name`
	- `_scan_folder_compat()` — מעביר `profile_config` ל-scan_folder
	- ניתוב לפי `ai_engine_type`: vision → scan_folder, document_intelligence → skip עם warning
- **src/pipeline/** — 5 מודולים (פורקו מ-scan_folder, 1,351 שורות סה"כ):
	- `archive_extractor.py` (121) — חילוץ ופתיחת ארכיונים
	- `drawing_processor.py` (202) — עיבוד שרטוטים (Vision API)
	- `pl_processor.py` (404) — עיבוד Parts List
	- `folder_saver.py` (290) — שמירת תוצרים לתיקיות
	- `results_merger.py` (334) — מיזוג תוצאות ויצוא Excel/B2B

### שכבת אינטגרציה למייל
- [src/services/email/graph_helper.py](src/services/email/graph_helper.py)
- [src/services/email/graph_mailbox.py](src/services/email/graph_mailbox.py)
- [email_connector_ews.py](email_connector_ews.py) (תמיכה חלופית)

### שכבת קונפיגורציה
- [src/core/config.py](src/core/config.py)
	- Azure, Email, מגבלות קבצים, הגדרות עיבוד
- [automation_config.json](automation_config.json)
	- פרמטרים תפעוליים של האוטומציה

---

## 4) זרימות עבודה עיקריות

### א) ניתוח ידני מתיקייה
1. משתמש בוחר תיקיית מקור
2. המערכת מסווגת קבצים (שרטוט/לא שרטוט)
3. קבצי שרטוט עוברים חילוץ בשלבים
4. נשמרים קבצי SUMMARY וקבצי B2B
5. אופציונלית נוצרת תיקיית TO_SEND עם קבצים ששונו/סוננו

### ב) עבודה מול תיבת מייל (פאנל מייל)
1. הגדרת תיבה משותפת
2. בדיקת חיבור
3. שליפת רשימת תיקיות
4. הורדת תוכן מתיקייה נבחרת
5. שליחה ידנית או שליחה מתיקייה מעובדת

### ג) אוטומציה מחזורית
1. טעינת הגדרות מתוך [automation_config.json](automation_config.json)
2. מעבר על רשימת תיבות משותפות (shared_mailboxes)
3. איתור תיקייה לפי שם או נתיב מלא
4. שליפת הודעות חדשות לפי State
5. הורדה, ניתוח, יצוא, העתקה ל-TO_SEND
6. שליחה אוטומטית (אם מופעל)
7. סימון הודעה כמעובדת בקטגוריה
8. עדכון State וכתיבה ללוג

---

## 5) מנוע הניתוח - פירוט מקצועי

קובץ מרכזי: [customer_extractor_v3_dual.py](customer_extractor_v3_dual.py) (987 שורות)

יכולות עיקריות:
- שימוש ב-Azure OpenAI (Vision API)
- OCR עם Tesseract, כולל עיבוד תמונה ושיפור ניגודיות
- זיהוי סיבוב ושיפור orientation
- תמיכה בלוגיקות לקוח ספציפיות (למשל IAI/RAFAEL)
- מנגנון Retry עם שיפור תמונה בשלבים
- ניטור עלויות (Token usage)

פונקציית העיבוד המרכזית:
- scan_folder(...) — 650 שורות
	- תומכת selected_stages
	- תומכת enable_image_retry
	- תומכת confidence_level עבור וריאנטי B2B
	- פרמטר `profile_config: Dict = None` — מגדיר prompts context ומאפס ביציאה
- מאצילה ל-5 מודולים ב-`src/pipeline/`:
	- archive_extractor → drawing_processor → pl_processor → folder_saver → results_merger

---

## 6) תוצרי מערכת (Outputs)

סוגי תוצרים עיקריים:
- SUMMARY_all_results_TIMESTAMP.xlsx
- SUMMARY_all_classifications_TIMESTAMP.xlsx
- קבצי B2B טקסטואליים (כולל וריאנטים)
- קבצים ממוספרים בפורמט B2B* לשילוח

תיקיות פעילות נפוצות:
- תיקיית הורדה (מוגדר ב-automation_config.json) — הורדות מייל
- [NEW FILES/](NEW%20FILES/) — תוצרים B2B (מתרוקנת אוטומטית)
- תיקיית דוחות (scheduler_report_folder) — דוח Excel מסכם לכל סבב

---

## 7) קונפיגורציה וקבצי מצב

### קבצי קונפיגורציה
- .env
	- מפתחות Azure (תמיכה ב-MODEL_{NAME}_ENDPOINT/KEY לכל מודל בנפרד)
	- פרטי Graph
	- הגדרות Email כלליות
- **configs/{profile}.json** — קונפיג לכל פרופיל בנפרד:
	- `configs/quotes.json` — הצעות מחיר
	- `configs/orders.json` — הזמנות
	- `configs/invoices.json` — חשבוניות
	- `configs/delivery.json` — תעודות משלוח
	- `configs/complaints.json` — תלונות
	- כל קובץ כולל: תיבות, תיקיות, תזמון, שלבים, מגבלות, שליחה
- [automation_config.json](automation_config.json)
	- Legacy config (quotes backward compatibility)
- [email_config.json](email_config.json)
	- כתובות שמורות לפאנל מייל

### קבצי מצב ולוג — **לכל פרופיל בנפרד**
- **data/{profile}/** — תיקיית state לכל פרופיל:
	- `data/{profile}/state.json` — last_checked_by_mailbox, processed_ids
	- `data/{profile}/status_log.txt` — לוג סטטוס (per-profile)
	- `data/{profile}/automation_log.jsonl` — רשומות ריצה
	- `data/{profile}/health.json` — מצב בריאות
	- `data/{profile}/alert.json` — התראות

---

## 8) תמיכה בתיבות מרובות (Multi-Mailbox)

המערכת תומכת בריבוי תיבות דרך:
- shared_mailboxes ב-[automation_config.json](automation_config.json)
- שדה תיבות משותפות בפאנל האוטומציה (מופרד פסיק/נקודה-פסיק/שורה חדשה)

התנהגות:
- כל תיבה מעובדת בנפרד בתוך אותו סבב
- State נשמר פר תיבה כדי למנוע כפילויות
- ניתן לבחור תיקייה לפי שם או נתיב מלא

---

## 9) טעינת תיקיות מתיבה - המצב הנוכחי

ב-[src/services/email/graph_mailbox.py](src/services/email/graph_mailbox.py) יש:
- טעינה עם Pagination מלאה (@odata.nextLink)
- טעינה רקורסיבית של כל עץ התיקיות
- תמיכה ב-includeHiddenFolders
- יצירת path מלא לתיקייה (למשל Inbox/Quotes/2026)

ב-[automation_panel_gui.py](automation_panel_gui.py):
- כפתור בדוק חיבור (בודק קישוריות בלבד)
- כפתור טען תיקיות (טוען רשימת תיקיות לבחירה)
- תיבת תיבה להצגה (לבחירת התיבה שממנה מציגים תיקיות)

---

## 10) מסך אוטומציה - שדות עיקריים

- תיבות משותפות
- תת-תיקייה (ComboBox עם תיקיות נטענות)
- נמען לשליחה
- תיקיית הורדה
- TO_SEND
- תיקיית שמירה
- דקות בין סבבים
- כמות מיילים לסבב
- מגבלות גודל קובץ ורזולוציה
- בחירת שלבים 1-5
- רמת ביטחון B2B (LOW/MEDIUM/HIGH)
- סימון קטגוריה למיילים מעובדים

---

## 11) תלותים עיקריים

- openai (Azure OpenAI)
- opencv-python
- pillow
- pandas
- pdfplumber
- numpy
- python-dotenv
- pytesseract
- requests

אופציונלי:
- easyocr
- pymupdf (fitz)

---

## 12) תקלות נפוצות ופתרון מהיר

### לא כל התיקיות נטענות
- לוודא בדוק חיבור -> טען תיקיות
- לבדוק הרשאות בתיבה ובתיקיות הספציפיות
- להשתמש בנתיב מלא אם יש שמות כפולים

### אין זיהוי OCR טוב
- לבדוק התקנת Tesseract
- להפעיל enable_retry
- לבדוק מגבלת רזולוציה נמוכה מדי

### אוטומציה לא מזהה מיילים חדשים
- לבדוק מצב ב-[automation_state.json](automation_state.json)
- לבצע Reset State מהפאנל אם צריך סריקה מחדש

---

## 13) אבטחה ותפעול

- אין לשמור מפתחות API בקבצים שנכנסים ל-Git
- רצוי לנהל .env לפי סביבת עבודה
- מומלץ גיבוי תקופתי ל-automation_config.json ול-automation_state.json
- מומלץ לנקות תיקיות זמניות וקבצי הורדה ישנים

---

## 14) כיווני המשך מומלצים

1. ~~פיצול customer_extractor_v3_dual.py למודולים קטנים~~ — ✅ בוצע (src/pipeline/ — 5 מודולים)
2. הוספת בדיקות רגרסיה קבועות ל-IAI/RAFAEL
3. הוספת דיאגנוסטיקה UI לתיקיות חסרות הרשאה
4. הרחבת דשבורד Streamlit עם ניתוח מגמות
5. מילוי prompts ל-4 פרופילים נוספים (orders, invoices, delivery, complaints)
6. מימוש Document Intelligence pipeline (`_run_once_di()` — כרגע stub)

---

## 15) קבצים מרכזיים לקריאה מהירה

- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)
- [streamlit_app/app.py](streamlit_app/app.py) — ★ Streamlit entry point
- [streamlit_app/pages/2_📊_Dashboard.py](streamlit_app/pages/2_📊_Dashboard.py) — דשבורד
- [customer_extractor_v3_dual.py](customer_extractor_v3_dual.py) — מנוע ליבה
- [automation_runner.py](automation_runner.py) — runner אוטומטי
- [src/services/extraction/drawing_pipeline.py](src/services/extraction/drawing_pipeline.py) — pipeline
- [src/services/email/graph_mailbox.py](src/services/email/graph_mailbox.py)
- [src/core/config.py](src/core/config.py)

