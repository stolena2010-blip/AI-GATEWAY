# מפת דרכים — פרופיל הזמנות לקוח (Orders)

> **סטטוס**: תכנון בלבד — אין ביצוע  
> **תאריך**: 2026-04-04  
> **מבוסס על**: תשתית Multi-Profile קיימת (v4.1)

---

## תיאור התהליך

הזמנת לקוח מגיעה למייל ומכילה:
- **מסמך הזמנה** (PDF / Word / Excel / גוף מייל) — טבלת פריטים עם מק"טים, כמויות, מחירים, תאריכי אספקה
- **שרטוטים** — לכל פריט: חומר גלם + תיאור עבודה בעברית
- **קבצים נוספים** — תמונות, מסמכים נלווים (כמו בהצעות מחיר)

### הבדלים מרכזיים מהצעת מחיר (Quotes)

| נושא | Quotes | Orders |
|-------|--------|--------|
| **מקור כמויות** | מייל / PL / הצעה | **מסמך ההזמנה בלבד** |
| **PL Processing** | Stage 6 — חילוץ + שיוך | **לא רלוונטי** |
| **פלט מהשרטוט** | מק"ט, ציפוי, צביעה, שטח | **חומר גלם + תיאור עבודה בעברית** |
| **פלט מההזמנה** | כמויות + תיאור (Stage 8) | **כמויות + מחירים + תאריכי אספקה** |
| **רמזור** | Confidence (HIGH/MED/LOW) | **מק"ט בהזמנה נמצא/לא נמצא בשרטוט** |
| **B2B** | 18 שדות, 3 וריאנטים | **דומה, עם שדות מחיר/אספקה** |

---

## שלבי Pipeline — Orders

```
Phase 0    Archive Extraction       (קיים — ללא שינוי)
Phase 0.5  Subfolder Discovery      (קיים — ללא שינוי)
Phase 1    File Classification      (Stage 0 — ללא שינוי)
                │
                ├── DRAWING  ──►  Phase 2: Drawing Extraction
                │                   Stage 1: מק"ט, שם פריט, לקוח
                │                   Stage 2: חומר גלם + תיאור עבודה (פרומפט חדש)
                │                   Stage 3: הערות (אופציונלי)
                │
                ├── PURCHASE_ORDER ──►  Phase 8: Order Table Extraction (פרומפט חדש)
                │                        - מק"ט, כמות, מחיר יחידה, סה"כ
                │                        - תאריך אספקה מבוקש
                │                        - תיאור פריט (fallback)
                │
                └── IMAGE/OTHER  ──►  שמירה בלבד
                │
Phase MATCH   Matching: מק"ט הזמנה ↔ מק"ט שרטוט     ◄── חדש
                │
                ├── ✅ MATCHED  → ירוק ברמזור
                └── ❌ UNMATCHED → אדום ברמזור
                │
Phase SAVE    Excel + B2B + Traffic Light Email       ◄── מותאם
```

---

## שלבים ליישום

### שלב 1 — פרומפטים (prompts/orders/)
> **מאמץ**: נמוך | **סיכון**: נמוך | **תלות**: אין

**1.1** העתק פרומפטים קיימים שלא משתנים:
```
prompts/quotes/ → prompts/orders/
├── 01_identify_drawing_layout.txt     ← ללא שינוי
├── 09_classify_document_type.txt      ← ללא שינוי
└── 10_detect_rotation.txt             ← ללא שינוי
```

**1.2** צור פרומפט `02_extract_basic_info.txt` מותאם:
- **שינוי**: בנוסף למק"ט + שם פריט → חלץ גם **חומר גלם** (material)
- במקום: ציפוי/צביעה/שטח גיאומטרי
- הוסף: "תאר את העבודה הנדרשת בעברית — כולל חומר גלם, עיבודים ותהליכים"

**1.3** צור פרומפט `03_extract_work_description.txt` (חדש):
- תיאור עבודה מפורט בעברית מתוך השרטוט
- חומר גלם (אלומיניום, פלדה, נירוסטה, פליז, וכו')
- עיבודים (חריטה, כרסום, השחזה, ניקוז, וכו')
- טיפולי חום / ציפוי אם מופיעים

**1.4** צור פרומפט `08_extract_order_items.txt` (מחליף את 08 הקיים):
- **שינוי מרכזי**: חלץ גם **מחיר יחידה**, **מחיר סה"כ**, **מט"ח**, **תאריך אספקה**
- JSON output:
```json
{
  "items": [
    {
      "item_number": "S3AP0004A",
      "quantities": ["189"],
      "unit_price": "12.50",
      "total_price": "2362.50",
      "currency": "ILS",
      "delivery_date": "2026-05-15",
      "work_description": "ציפוי קשיח..."
    }
  ]
}
```

---

### שלב 2 — Stage Configuration
> **מאמץ**: נמוך | **סיכון**: נמוך | **תלות**: שלב 1

**2.1** עדכון `configs/orders.json`:
```json
"ai_engine": {
  "stages": [0, 1, 2, 3, 8],
  "stage_models": {
    "0": "gpt-4o-vision",
    "1": "gpt-5.4",
    "2": "gpt-5.4",
    "3": "gpt-5.4",
    "8": "gpt-5.4"
  },
  "prompts_folder": "prompts/orders",
  "skip_pl": true,
  "skip_area": true
}
```

**2.2** Stages שלא ירוצו:
- ~~Stage 4~~ (שטח גיאומטרי — לא רלוונטי)
- ~~Stage 5~~ (BOM validation — לא רלוונטי)
- ~~Stage 6~~ (PL — לא רלוונטי)
- ~~Stage 7~~ (כמויות מהמייל — לוקחים מההזמנה)
- ~~Stage 9~~ (merge תיאורים — הלוגיקה שונה)

---

### שלב 3 — Order Item Extractor מותאם
> **מאמץ**: בינוני | **סיכון**: בינוני | **תלות**: שלב 1

**3.1** הרחבת `_extract_item_details_from_documents()` ב-`document_reader.py`:
- תמיכה ב-Word (`.docx`) — כרגע רק PDF + תמונה
- תמיכה באקסל (`.xlsx`) — קריאה ישירה של טבלה ללא Vision API
- תמיכה בגוף המייל (HTML/text) — חילוץ טבלה מ-email_data

**3.2** שדות חדשים ב-output:
```python
item_details[item_number] = {
    'quantities': ["189"],
    'work_description': "ציפוי קשיח...",
    'unit_price': "12.50",         # ← חדש
    'total_price': "2362.50",      # ← חדש
    'currency': "ILS",             # ← חדש
    'delivery_date': "2026-05-15", # ← חדש
}
```

**3.3** Fallback chain לכמויות:
```
1. טבלת הזמנה (PDF/Word/Excel) → מקור ראשי
2. גוף המייל (טבלה ב-HTML)     → fallback
3. טקסט חופשי במייל              → fallback אחרון
```

---

### שלב 4 — Matching Engine (חדש)
> **מאמץ**: בינוני | **סיכון**: נמוך | **תלות**: שלב 3

**4.1** פונקציה חדשה: `match_order_to_drawings()`

```python
def match_order_to_drawings(
    order_items: Dict[str, Any],      # מק"טים מההזמנה
    drawing_results: List[Dict],       # מק"טים מהשרטוטים
) -> List[Dict]:
    """
    Returns list of matches:
    {
        "order_item_number": "S3AP0004A",
        "drawing_part_number": "S3AP0004A",
        "match_type": "exact" | "fuzzy" | "none",
        "match_score": 1.0,
        "status": "green" | "red"
    }
    """
```

**4.2** לוגיקת התאמה (priority order):
1. **Exact match** — מק"ט זהה (case-insensitive, stripped)
2. **Normalized match** — הסרת מקפים, רווחים, leading zeros
3. **Partial match** — מק"ט מוכל בשם קובץ או drawing_number
4. **No match** — 🔴 אדום ברמזור

**4.3** מיקום בקוד: `src/pipeline/order_matcher.py` (מודול חדש)

---

### שלב 5 — B2B מותאם להזמנות
> **מאמץ**: נמוך-בינוני | **סיכון**: נמוך | **תלות**: שלב 3, 4

**5.1** הרחבת B2B fields ב-`b2b_export.py`:
- שדה 6: **מחיר יחידה** (במקום "0.0000")
- שדה 7: **מט"ח** (במקום "0")
- שדה 8: **תאריך אספקה** (כבר קיים — מילוי אמיתי)
- שדה חדש (19?): **match_status** — "MATCHED" / "UNMATCHED"

**5.2** B2B confidence logic for orders:
- `B2B-0_*.txt` — כל הפריטים
- `B2BH-0_*.txt` — רק MATCHED (ירוק)
- `B2BM-0_*.txt` — MATCHED + PARTIAL

---

### שלב 6 — רמזור (Traffic Light Email)
> **מאמץ**: בינוני | **סיכון**: נמוך | **תלות**: שלב 4

**6.1** HTML table חדש בפונקציה `_build_email_body_html()`:

```
╔════════════╦══════════╦════════╦═══════╦══════════╦══════════╗
║   מק"ט     ║  כמות    ║ מחיר   ║ אספקה ║  שרטוט   ║  סטטוס   ║
╠════════════╬══════════╬════════╬═══════╬══════════╬══════════╣
║ S3AP0004A  ║   189    ║ 12.50  ║ 15/5  ║ S3AP...  ║ 🟢 נמצא  ║
║ L76108A    ║    10    ║  8.00  ║ 20/5  ║   —      ║ 🔴 חסר   ║
╚════════════╩══════════╩════════╩═══════╩══════════╩══════════╝
```

**6.2** לוגיקת צבעים:
| סטטוס | צבע | משמעות |
|--------|------|---------|
| 🟢 ירוק | `#27AE60` | מק"ט מההזמנה נמצא בשרטוט |
| 🟡 צהוב | `#F1C40F` | התאמה חלקית (fuzzy) |
| 🔴 אדום | `#E74C3C` | מק"ט מההזמנה **לא** נמצא באף שרטוט |
| ⚪ אפור | `#95A5A6` | שרטוט ללא מק"ט תואם בהזמנה |

**6.3** סיכום מעל הטבלה:
```
הזמנת לקוח: 12 פריטים | 10 נמצאו בשרטוטים ✅ | 2 חסרים ❌
```

---

### שלב 7 — אינטגרציה ב-scan_folder
> **מאמץ**: בינוני | **סיכון**: גבוה | **תלות**: שלב 1-6

**7.1** הוספת Phase חדש ב-`customer_extractor_v3_dual.py`:
```python
# Phase MATCH (orders profile only)
if profile_name == "orders" and order_items:
    match_results = match_order_to_drawings(order_items, subfolder_results)
    for result in subfolder_results:
        result['match_status'] = _get_match_status(result, match_results)
```

**7.2** הזרמת שדות חדשים דרך ה-pipeline:
```
document_reader → order_items (כמויות, מחירים, אספקה)
       ↓
drawing_processor → drawing_results (מק"ט, חומר, עבודה)
       ↓
order_matcher → match_results (ירוק/אדום)
       ↓
folder_saver → Excel + B2B (עם שדות הזמנה)
       ↓
results_merger → SUMMARY
       ↓
automation_runner → Traffic Light Email
```

**7.3** שינוי ב-`folder_saver.py`:
- Excel: עמודות נוספות (`unit_price`, `currency`, `delivery_date`, `match_status`)
- B2B: שדות מחיר/אספקה מלאים

---

### שלב 8 — Email Config & Automation
> **מאמץ**: נמוך | **סיכון**: נמוך | **תלות**: שלב 7

**8.1** עדכון `configs/orders.json`:
```json
"email": {
  "shared_mailbox": "orders@algat.co.il",
  "shared_mailboxes": ["orders@algat.co.il"],
  "inbox_folder": "תיבת דואר נכנס",
  "category_processed": "AI ORD DONE",
  "category_processed_color": "preset20"
}
```

**8.2** הפעלת scheduler ב-orders profile

**8.3** הוספת `_build_order_email_body_html()` ב-`automation_runner.py`:
- טבלת רמזור (שלב 6) במקום טבלת confidence הקיימת
- סיכום מחירים כולל
- רשימת שרטוטים חסרים

---

## סדר עבודה מומלץ

```
שלב 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
  │       │     │     │     │     │     │     │
  │       │     │     │     │     │     │     └── Email + Scheduler
  │       │     │     │     │     │     └── Pipeline integration
  │       │     │     │     │     └── Traffic light HTML
  │       │     │     │     └── B2B adaptation
  │       │     │     └── Order↔Drawing matching
  │       │     └── Order extraction (PDF/Word/Excel/email)
  │       └── Config + stages
  └── Prompts
```

**נקודות ביקורת (checkpoints):**
- ✅ אחרי שלב 2: ריצה ידנית על תיקיית הזמנה — וידוא שסיווג + חילוץ בסיסי עובדים
- ✅ אחרי שלב 4: בדיקת matching על 5 הזמנות אמיתיות
- ✅ אחרי שלב 6: שליחת מייל רמזור לדוגמה
- ✅ אחרי שלב 8: ריצה אוטומטית end-to-end

---

## מה לא צריך לשנות

| רכיב | סיבה |
|-------|--------|
| `drawing_processor.py` | עובד as-is — Stage 1-4 נשלט ע"י stages config |
| `results_merger.py` | generic — מאחד כל סוג Excel |
| `file_classifier.py` | כבר מזהה PURCHASE_ORDER |
| `automation_runner.py` loop | Multi-profile infrastructure קיימת |
| `prompt_loader.py` | כבר תומך ב-`prompts_folder` per profile |
| שינוי שמות קבצים | אותו mechanism כמו quotes — `file_renamer.py` |

---

## הערכת סיכון

| סיכון | הסתברות | השפעה | מיטיגציה |
|--------|----------|--------|----------|
| פורמט הזמנה לא צפוי | גבוהה | בינוני | Prompt engineering iterativi + fallback chain |
| Word/Excel parsing | בינוני | בינוני | python-docx + openpyxl — ספריות יציבות |
| Fuzzy matching שגוי | נמוך | גבוה | Threshold + manual override flag |
| פגיעה ב-quotes pipeline | נמוך | קריטי | Profile isolation + regression tests (430 existing) |
