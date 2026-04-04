"""
🚀 Automation — AI GATEWAY KITARON
Per-profile automation control panel — each document type has its own tab
with dedicated settings (email, AI engine, run, log).
"""
import streamlit as st
import sys
from pathlib import Path
from datetime import time as dt_time, datetime as _dt

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from streamlit_app.backend.config_manager import (
    load_config, save_config, reset_state,
    load_all_profiles, load_profile_config, save_profile_config,
    reset_profile_state,
)
from streamlit_app.backend.email_helpers import (
    parse_mailboxes_text, test_all_mailboxes,
    load_folders_for_mailbox, format_folder_label,
)
from streamlit_app.backend.runner_bridge import get_runner_bridge, get_pipeline_bridge
from streamlit_app.backend.log_reader import read_log_tail, get_countdown, detect_active_run
from streamlit_app.brand import BRAND_CSS, brand_header, sidebar_logo, profile_banner, profile_tab_css, get_profile_color


def _is_time_in_range(now_time, start_time, end_time) -> bool:
    if start_time <= end_time:
        return start_time <= now_time < end_time
    else:
        return now_time >= start_time or now_time < end_time


st.set_page_config(page_title="🚀 אוטומציה — AI GATEWAY KITARON", page_icon="🌿", layout="wide")
st.markdown(BRAND_CSS, unsafe_allow_html=True)
sidebar_logo()

# ═══════════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════════
for _k, _d in [
    ("runner", None), ("is_running", False),
    ("status_msg", "מוכן"), ("log_lines", []),
    ("confirm_reset", False), ("pipeline_bridge", None),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _d

# Per-profile folder state
_all_profiles = load_all_profiles()
for _p in _all_profiles:
    _pn = _p["profile_name"]
    for _sk, _sd in [
        (f"folders_loaded_{_pn}", []),
        (f"folders_mailbox_{_pn}", ""),
        (f"confirm_reset_{_pn}", False),
    ]:
        if _sk not in st.session_state:
            st.session_state[_sk] = _sd

# ═══════════════════════════════════════════════════════════════════
# MODULE-LEVEL CONSTANTS
# ═══════════════════════════════════════════════════════════════════
_CATEGORY_COLOR_MAP = {
    "None": "preset0", "Red": "preset1", "Orange": "preset2",
    "Brown": "preset3", "Yellow": "preset4", "Green": "preset5",
    "Teal": "preset6", "Olive": "preset7", "Blue": "preset8",
    "Purple": "preset9", "Pink": "preset10", "Gray": "preset11",
    "Dark Red": "preset12", "Dark Orange": "preset13", "Dark Brown": "preset14",
    "Dark Yellow": "preset15", "Dark Green": "preset16", "Dark Teal": "preset17",
    "Dark Olive": "preset18", "Dark Blue": "preset19", "Dark Purple": "preset20",
    "Dark Pink": "preset21", "Dark Gray": "preset22", "Black": "preset23",
    "Light Gray": "preset24", "Light Blue": "preset25",
}
_REVERSE_COLOR_MAP = {v: k for k, v in _CATEGORY_COLOR_MAP.items()}
_COLOR_NAMES = list(_CATEGORY_COLOR_MAP.keys())

_RESOLUTION_MAP = {
    "2048 (מהיר - OCR טוב)": 2048,
    "3072 (מאזן - איכות מעולה)": 3072,
    "4096 (איכות - OCR מושלם)": 4096,
    "12000 (Overkill - ברזולוציה מקסימה)": 12000,
}
_REVERSE_RES_MAP = {v: k for k, v in _RESOLUTION_MAP.items()}

_AVAILABLE_MODELS = sorted({
    "gpt-4o-vision", "gpt-4o-mini-email", "o4-mini", "gpt-5.2", "gpt-5.4"
})
_DI_MODELS = ["prebuilt-invoice", "prebuilt-layout", "prebuilt-receipt", "prebuilt-document"]
_VALIDATE_MODELS = ["gpt-4o-mini", "gpt-4o", "o4-mini"]

_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    try:
        for line in _env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if value and key.startswith("STAGE_") and key.endswith("_MODEL"):
                _AVAILABLE_MODELS.append(value)
            elif key == "AZURE_OPENAI_DEPLOYMENT" and value:
                _AVAILABLE_MODELS.append(value)
        _AVAILABLE_MODELS = sorted(set(_AVAILABLE_MODELS))
    except Exception:
        pass

_ENV_STAGE_DEFAULTS = {}
if _env_path.exists():
    try:
        for line in _env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if value and key.startswith("STAGE_") and key.endswith("_MODEL"):
                try:
                    stage_num = int(key.split("_")[1])
                    _ENV_STAGE_DEFAULTS[stage_num] = value
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass
for _n in range(10):
    if _n not in _ENV_STAGE_DEFAULTS:
        _ENV_STAGE_DEFAULTS[_n] = "gpt-4o-vision"


# ═══════════════════════════════════════════════════════════════════
# PIPELINE BRIDGE HELPER
# ═══════════════════════════════════════════════════════════════════
def _get_bridge():
    if st.session_state.pipeline_bridge is None:
        st.session_state.pipeline_bridge = get_pipeline_bridge()
    return st.session_state.pipeline_bridge


# ═══════════════════════════════════════════════════════════════════
# BRANDED HEADER + GLOBAL STATUS
# ═══════════════════════════════════════════════════════════════════
st.html(brand_header("אוטומציה — AI GATEWAY KITARON"))
st.html(profile_tab_css())

@st.fragment(run_every=5)
def _global_status_fragment():
    """Shows running status for all profiles."""
    bridge = _get_bridge()
    statuses = bridge.get_all_status()
    running = [s["display_name"] for s in statuses.values() if s["running"]]
    scheduled = [s["display_name"] for s in statuses.values() if s.get("scheduler")]
    parts = []
    if running:
        parts.append(f'<span class="run-badge run-badge-active">🟢 פעיל: {", ".join(running)}</span>')
    if scheduled:
        parts.append(f'<span class="run-badge" style="background:#2d5a27;color:#7fff00;padding:4px 12px;border-radius:12px;">🕐 תזמון: {", ".join(scheduled)}</span>')
    if parts:
        st.markdown(" ".join(parts), unsafe_allow_html=True)
    else:
        st.markdown(
            '<span class="run-badge run-badge-inactive">🔴 אין פרופילים פעילים</span>',
            unsafe_allow_html=True,
        )

_global_status_fragment()

# ═══════════════════════════════════════════════════════════════════
# PROFILE TABS — one per document type
# ═══════════════════════════════════════════════════════════════════
_PROFILE_ICONS = {
    "quotes": "📐", "orders": "📦", "invoices": "🧾",
    "delivery": "🚚", "complaints": "📣",
}

profiles = load_all_profiles()
if not profiles:
    st.warning("לא נמצאו פרופילים בתיקיית configs/")
    st.stop()

tab_labels = [f'{_PROFILE_ICONS.get(p["profile_name"], "📄")} {p["display_name"]}' for p in profiles]
profile_tabs = st.tabs(tab_labels)


def _render_profile_tab(profile: dict, tab_index: int):
    """Render settings & controls for a single profile inside its tab."""
    pn = profile["profile_name"]
    cfg = load_profile_config(pn)
    if not cfg:
        st.error(f"לא נמצא קובץ הגדרות עבור {pn}")
        return

    # ── Profile banner ──
    st.html(profile_banner(pn))

    # ── Visual reminder for non-quotes profiles ──
    if pn != "quotes":
        pc = get_profile_color(pn)
        st.html(f"""
        <div style="
            background: linear-gradient(90deg, {pc['bg']} 0%, rgba(239,68,68,0.08) 100%);
            border: 2px solid {pc['accent']};
            border-right: 6px solid #ef4444;
            border-radius: 10px;
            padding: 10px 18px;
            margin-bottom: 12px;
            direction: rtl;
            display: flex;
            align-items: center;
            gap: 12px;
        ">
            <span style="font-size:22px;">⚠️</span>
            <span style="font-size:15px; font-weight:700; color:#fbbf24;">
                שימו לב! את/ה עובד/ת על תהליך
                <span style="color:{pc['accent']}; font-weight:900;">{pc['icon']} {pc['label']}</span>
                — לא הצעות מחיר!
            </span>
        </div>
        """)

    engine_type = cfg.get("ai_engine", {}).get("type", "vision")
    email_cfg = cfg.get("email", {})
    folders_cfg = cfg.get("folders", {})
    ai_cfg = cfg.get("ai_engine", {})
    output_cfg = cfg.get("output", {})
    processing_cfg = cfg.get("processing", {})
    scheduler_cfg = cfg.get("scheduler", {})
    validation_cfg = cfg.get("validation", {})
    review_cfg = cfg.get("review", {})

    # ── Action buttons per profile ──
    btn = st.columns(7)
    with btn[0]:
        save_btn = st.button("💾 שמור", key=f"save_{pn}", width="stretch")
    with btn[1]:
        test_btn = st.button("🔌 בדוק חיבור", key=f"test_{pn}", width="stretch")
    with btn[2]:
        run_btn = st.button("▶️ הרץ סבב", key=f"run_{pn}", width="stretch")
    with btn[3]:
        run_heavy_btn = st.button("🏋️ הרץ כבדים", key=f"heavy_{pn}", width="stretch")
    with btn[4]:
        start_btn = st.button("🚀 הפעל", key=f"start_{pn}", width="stretch")
    with btn[5]:
        stop_btn = st.button("⏹ עצור הכל", key=f"stop_{pn}", width="stretch")
    with btn[6]:
        if st.session_state.get(f"confirm_reset_{pn}", False):
            reset_btn = st.button("⚠️ לחץ שוב לאישור", key=f"reset_{pn}", width="stretch", type="primary")
        else:
            reset_btn = st.button("🔄 Reset", key=f"reset_{pn}", width="stretch")

    # Running / scheduler indicator
    bridge = _get_bridge()
    _badges = []
    if bridge.is_running(pn):
        _badges.append(f'<span class="run-badge run-badge-active">🟢 {profile["display_name"]}: פעיל</span>')
    if bridge.is_scheduler_active(pn):
        _badges.append(f'<span class="run-badge" style="background:#2d5a27;color:#7fff00;padding:4px 12px;border-radius:12px;">🕐 תזמון: פעיל</span>')
    if _badges:
        st.markdown(" ".join(_badges), unsafe_allow_html=True)

    # ── Inner tabs: settings sections ──
    if engine_type == "vision":
        inner_tabs = st.tabs(["📧 מייל ותיקיות", "🔬 שלבים ומודלים", "⏱ הגדרות ריצה", "📋 לוג"])
    else:
        inner_tabs = st.tabs(["📧 מייל ותיקיות", "🤖 מנוע AI", "⏱ הגדרות ריצה", "📋 לוג"])

    # ╔════════════════════════════════════════════════╗
    # ║  INNER TAB 1 — EMAIL + FOLDERS                ║
    # ╚════════════════════════════════════════════════╝
    with inner_tabs[0]:
        col_mail, col_folders = st.columns([1, 1])

        with col_mail:
            st.subheader("📧 הגדרות מייל")

            mailboxes_str = st.text_input(
                "תיבות משותפות (מופרדות בפסיק):",
                value=", ".join(email_cfg.get("shared_mailboxes", [])) or email_cfg.get("shared_mailbox", ""),
                key=f"mailboxes_{pn}",
            )
            parsed_mboxes = parse_mailboxes_text(mailboxes_str)

            mc1, mc2 = st.columns([3, 1])
            with mc1:
                sel_mbox = st.selectbox(
                    "תיבה להצגה:", options=parsed_mboxes if parsed_mboxes else [""],
                    index=0, key=f"sel_mbox_{pn}",
                )
            with mc2:
                st.markdown("<br>", unsafe_allow_html=True)
                load_f_btn = st.button("📂 טען תיקיות", key=f"load_folders_{pn}", width="stretch")

            if load_f_btn and sel_mbox:
                with st.spinner(f"טוען תיקיות עבור {sel_mbox}..."):
                    _folders, _err = load_folders_for_mailbox(sel_mbox)
                    if _err:
                        st.error(_err)
                    else:
                        st.session_state[f"folders_loaded_{pn}"] = _folders
                        st.session_state[f"folders_mailbox_{pn}"] = sel_mbox
                        st.success(f"נטענו {len(_folders)} תיקיות עבור {sel_mbox}")

            folder_options = []
            folder_path_map = {}
            loaded_folders = st.session_state.get(f"folders_loaded_{pn}", [])
            if loaded_folders:
                for f in loaded_folders:
                    label = format_folder_label(f["path"], f.get("totalItemCount"))
                    folder_options.append(label)
                    folder_path_map[label] = f["path"]

            current_folder = email_cfg.get("inbox_folder", "Inbox")
            if folder_options:
                default_idx = 0
                for i, opt in enumerate(folder_options):
                    raw_path = folder_path_map.get(opt, opt)
                    if raw_path == current_folder or opt.startswith(current_folder):
                        default_idx = i
                        break
                sel_folder_label = st.selectbox("תת-תיקייה:", options=folder_options, index=default_idx, key=f"folder_sel_{pn}")
                sel_folder = folder_path_map.get(sel_folder_label, sel_folder_label)
            else:
                sel_folder = st.text_input("תת-תיקייה:", value=current_folder, key=f"folder_txt_{pn}")

            rc1, rc2 = st.columns(2)
            with rc1:
                rerun_folder = st.text_input("תיקיית RERUN:", value=email_cfg.get("rerun_folder_name", ""), key=f"rerun_folder_{pn}")
            with rc2:
                rerun_mailbox = st.text_input("תיבת RERUN:", value=email_cfg.get("rerun_mailbox", ""), key=f"rerun_mbox_{pn}")

            scan_from = st.text_input("סרוק מתאריך (DD/MM/YYYY HH:MM):", value=email_cfg.get("scan_from_date", ""), key=f"scan_from_{pn}")

            cat_c1, cat_c2 = st.columns(2)
            with cat_c1:
                cat_processed = st.text_input("קטגוריה מעובד:", value=email_cfg.get("category_processed", "AI Processed"), key=f"cat_proc_{pn}")
            with cat_c2:
                stored_color = email_cfg.get("category_processed_color", "preset20")
                cat_proc_color = st.selectbox(
                    "צבע:", options=_COLOR_NAMES,
                    index=_COLOR_NAMES.index(_REVERSE_COLOR_MAP.get(stored_color, "None")),
                    key=f"cat_proc_color_{pn}",
                )
            cat_c3, cat_c4 = st.columns(2)
            with cat_c3:
                cat_error = st.text_input("קטגוריה שגיאה:", value=email_cfg.get("category_error", "NO DRAW"), key=f"cat_err_{pn}")
            with cat_c4:
                stored_err_color = email_cfg.get("category_error_color", "preset1")
                cat_err_color = st.selectbox(
                    "צבע שגיאה:", options=_COLOR_NAMES,
                    index=_COLOR_NAMES.index(_REVERSE_COLOR_MAP.get(stored_err_color, "None")),
                    key=f"cat_err_color_{pn}",
                )

            skip_senders = st.text_area(
                "דלג על שולחים (כתובת בכל שורה):",
                value="\n".join(email_cfg.get("skip_senders", [])), height=60, key=f"skip_senders_{pn}",
            )
            skip_categories = st.text_area(
                "דלג על קטגוריות (שם בכל שורה):",
                value="\n".join(email_cfg.get("skip_categories", [])), height=60, key=f"skip_cats_{pn}",
            )

        with col_folders:
            st.subheader("📁 תיקיות")
            download_dir = st.text_input("תיקיית הורדה:", value=folders_cfg.get("download", ""), key=f"dl_dir_{pn}")
            if download_dir and not Path(download_dir).exists():
                st.warning("⚠️ התיקייה לא קיימת")
            output_dir = st.text_input("תיקיית פלט:", value=folders_cfg.get("output", ""), key=f"out_dir_{pn}")
            archive_dir = st.text_input("תיקיית ארכיב:", value=folders_cfg.get("archive", ""), key=f"arc_dir_{pn}")
            tosend_dir = st.text_input("TO_SEND:", value=folders_cfg.get("to_send", ""), key=f"tosend_dir_{pn}")

            if engine_type == "vision":
                st.divider()
                st.subheader("📤 פלט")
                send_to = st.text_input("נמען לשליחה:", value=output_cfg.get("send_to", ""), key=f"send_to_{pn}")
                send_cc = st.text_input("CC:", value=output_cfg.get("send_cc", ""), key=f"send_cc_{pn}")
                b2b_conf = st.radio(
                    "רמת ביטחון B2B:", options=["LOW", "MEDIUM", "HIGH"],
                    index=["LOW", "MEDIUM", "HIGH"].index(output_cfg.get("b2b_confidence_level", "LOW") or "LOW"),
                    horizontal=True, key=f"b2b_conf_{pn}",
                )
            else:
                st.divider()
                st.subheader("📤 פלט")
                send_to = st.text_input("נמען לשליחה:", value=output_cfg.get("send_to", ""), key=f"send_to_{pn}")
                send_cc = st.text_input("CC:", value=output_cfg.get("send_cc", ""), key=f"send_cc_{pn}")
                b2b_conf = None

    # ╔════════════════════════════════════════════════╗
    # ║  INNER TAB 2 — AI ENGINE SETTINGS             ║
    # ╚════════════════════════════════════════════════╝
    with inner_tabs[1]:
        if engine_type == "vision":
            # ── Vision stages + models (like original) ──
            st.subheader("🔬 שלבי חילוץ ומודלים")

            stage_defs = [
                (0, "0: זיהוי", False), (1, "1: בסיסי", True),
                (2, "2: תהליכים", True), (3, "3: NOTES", True),
                (4, "4: שטח", True), (5, "5: Fallback", True),
                (6, "6: PL", True), (7, "7: email", True),
                (8, "8: הזמנות", True), (9, "9: מיזוג", True),
            ]
            saved_stages = {str(s): True for s in ai_cfg.get("stages", [])}
            saved_models = ai_cfg.get("stage_models", {})
            stage_enabled = {}
            stage_models = {}

            cols_r1 = st.columns(5)
            for i, (sn, label, has_cb) in enumerate(stage_defs[:5]):
                with cols_r1[i]:
                    if has_cb:
                        stage_enabled[sn] = st.checkbox(label, value=bool(saved_stages.get(str(sn), False)), key=f"stg_{sn}_{pn}")
                    else:
                        st.markdown(f"**{label}**")
                        stage_enabled[sn] = True
                    md = saved_models.get(str(sn), _ENV_STAGE_DEFAULTS.get(sn, "gpt-4o-vision"))
                    mi = _AVAILABLE_MODELS.index(md) if md in _AVAILABLE_MODELS else 0
                    stage_models[sn] = st.selectbox("מודל", options=_AVAILABLE_MODELS, index=mi, key=f"mdl_{sn}_{pn}", label_visibility="collapsed")

            cols_r2 = st.columns(5)
            for i, (sn, label, has_cb) in enumerate(stage_defs[5:]):
                with cols_r2[i]:
                    if has_cb:
                        stage_enabled[sn] = st.checkbox(label, value=bool(saved_stages.get(str(sn), False)), key=f"stg_{sn}_{pn}")
                    md = saved_models.get(str(sn), _ENV_STAGE_DEFAULTS.get(sn, "gpt-4o-vision"))
                    mi = _AVAILABLE_MODELS.index(md) if md in _AVAILABLE_MODELS else 0
                    stage_models[sn] = st.selectbox("מודל", options=_AVAILABLE_MODELS, index=mi, key=f"mdl_{sn}_{pn}", label_visibility="collapsed")

            with st.expander("⚙️ הגדרות מתקדמות"):
                ac1, ac2 = st.columns(2)
                with ac1:
                    stored_dim = ai_cfg.get("max_image_dimension", 4096)
                    dim_label = _REVERSE_RES_MAP.get(stored_dim, "4096 (איכות - OCR מושלם)")
                    max_img_dim = st.selectbox(
                        "מקסימום רזולוציה:", options=list(_RESOLUTION_MAP.keys()),
                        index=list(_RESOLUTION_MAP.keys()).index(dim_label) if dim_label in _RESOLUTION_MAP else 2,
                        key=f"max_dim_{pn}",
                    )
                    s1_skip = st.number_input("דילוג Retry שלב 1 (px):", value=int(ai_cfg.get("stage1_skip_retry_resolution_px", 8000)), min_value=0, key=f"s1skip_{pn}")
                    scan_dpi = st.selectbox("DPI:", options=[150, 200, 300], index=[150, 200, 300].index(int(ai_cfg.get("scan_dpi", 200))), key=f"dpi_{pn}")
                with ac2:
                    max_retries = st.number_input("ניסיונות חוזרים:", value=int(ai_cfg.get("max_retries", 3)), min_value=1, max_value=5, key=f"retries_{pn}")
                    iai_top_red = st.checkbox("IAI top-red fallback", value=ai_cfg.get("iai_top_red_fallback", False), key=f"iai_{pn}")
                    enable_ocr = st.checkbox("OCR", value=ai_cfg.get("enable_ocr", True), key=f"ocr_{pn}")

        else:
            # ── Document Intelligence settings ──
            st.subheader("🤖 מנוע Document Intelligence")

            di_c1, di_c2 = st.columns(2)
            with di_c1:
                cur_di = ai_cfg.get("di_model", "prebuilt-invoice")
                di_model = st.selectbox(
                    "מודל DI:", options=_DI_MODELS,
                    index=_DI_MODELS.index(cur_di) if cur_di in _DI_MODELS else 0,
                    key=f"di_model_{pn}",
                )
            with di_c2:
                cur_val = ai_cfg.get("validate_model", "gpt-4o-mini")
                validate_model = st.selectbox(
                    "מודל אימות GPT:", options=_VALIDATE_MODELS,
                    index=_VALIDATE_MODELS.index(cur_val) if cur_val in _VALIDATE_MODELS else 0,
                    key=f"val_model_{pn}",
                )

            st.divider()
            st.subheader("✅ ולידציה")
            val_c1, val_c2 = st.columns(2)
            with val_c1:
                use_sql = st.checkbox("SQL Server lookup", value=validation_cfg.get("use_sql_server", False), key=f"use_sql_{pn}")
                supplier_lookup = st.checkbox("חיפוש ספק", value=validation_cfg.get("supplier_lookup", False), key=f"sup_lookup_{pn}")
                po_matching = st.checkbox("התאמת הזמנה", value=validation_cfg.get("po_matching", False), key=f"po_match_{pn}")
            with val_c2:
                price_tol = st.number_input("סטיית מחיר (%):", value=int(validation_cfg.get("price_tolerance_percent", 5)), min_value=0, max_value=50, key=f"price_tol_{pn}")

            if review_cfg:
                st.divider()
                st.subheader("👁 סקירה")
                review_enabled = st.checkbox("דרוש אישור ידני", value=review_cfg.get("enabled", True), key=f"review_en_{pn}")
                auto_approve = st.checkbox("אישור אוטומטי", value=review_cfg.get("auto_approve_enabled", False), key=f"auto_appr_{pn}")

            # Keep variables for save — not used by vision
            stage_enabled = {}
            stage_models = {}
            max_img_dim = None
            s1_skip = 0
            scan_dpi = 200
            max_retries = int(ai_cfg.get("max_retries", 3))
            iai_top_red = False
            enable_ocr = False

    # ╔════════════════════════════════════════════════╗
    # ║  INNER TAB 3 — RUN SETTINGS                   ║
    # ╚════════════════════════════════════════════════╝
    with inner_tabs[2]:
        st.subheader("⏱ הגדרות ריצה")

        r1, r2, r3 = st.columns(3)
        with r1:
            scan_interval = st.number_input("דקות בין סבבים:", value=int(email_cfg.get("scan_interval_minutes", 5)), min_value=1, max_value=120, key=f"interval_{pn}")
        with r2:
            max_msgs = st.number_input("כמות מיילים לסבב:", value=int(email_cfg.get("max_messages_per_cycle", 200)), min_value=1, max_value=5000, key=f"max_msgs_{pn}")
        with r3:
            max_files = st.number_input("מקסימום קבצים למייל:", value=int(email_cfg.get("max_files_per_email", 15)), min_value=0, max_value=100, key=f"max_files_{pn}")

        chk = st.columns(4)
        with chk[0]:
            recursive = st.checkbox("כולל תת-תיקיות", value=processing_cfg.get("recursive", True), key=f"recursive_{pn}")
        with chk[1]:
            cleanup = st.checkbox("מחק אחרי העברה", value=processing_cfg.get("cleanup_download", True), key=f"cleanup_{pn}")
        with chk[2]:
            mark_proc = st.checkbox("סמן מעובד", value=processing_cfg.get("mark_as_processed", True), key=f"mark_proc_{pn}")
        with chk[3]:
            debug_mode = st.checkbox("Debug mode", value=processing_cfg.get("debug_mode", False), key=f"debug_{pn}")

        auto_chk = st.columns(3)
        with auto_chk[0]:
            auto_send = st.checkbox("שלח אוטומטית", value=output_cfg.get("auto_send", False), key=f"auto_send_{pn}")
        with auto_chk[1]:
            archive_full = st.checkbox("שמור עותק מלא", value=processing_cfg.get("archive_full", False), key=f"archive_{pn}")
        with auto_chk[2]:
            gen_excel = st.checkbox("הפק Excel", value=output_cfg.get("generate_excel", True), key=f"gen_excel_{pn}")

        with st.expander("🕐 תזמון אוטומטי (Scheduler)", expanded=scheduler_cfg.get("enabled", False)):
            sched_enabled = st.checkbox("הפעל תזמון אוטומטי", value=scheduler_cfg.get("enabled", False), key=f"sched_en_{pn}")

            sc1, sc2 = st.columns(2)
            with sc1:
                st.markdown("**▶️ רגילה**")
                _reg_from = scheduler_cfg.get("regular_from", "07:00") or "07:00"
                _reg_to = scheduler_cfg.get("regular_to", "19:00") or "19:00"
                sched_reg_from = st.time_input("משעה:", value=dt_time(*map(int, _reg_from.split(":"))), key=f"sched_rf_{pn}")
                sched_reg_to = st.time_input("עד שעה:", value=dt_time(*map(int, _reg_to.split(":"))), key=f"sched_rt_{pn}")
            with sc2:
                st.markdown("**🏋️ כבדה**")
                _hvy_from = scheduler_cfg.get("heavy_from", "19:00") or "19:00"
                _hvy_to = scheduler_cfg.get("heavy_to", "07:00") or "07:00"
                sched_hvy_from = st.time_input("משעה:", value=dt_time(*map(int, _hvy_from.split(":"))), key=f"sched_hf_{pn}")
                sched_hvy_to = st.time_input("עד שעה:", value=dt_time(*map(int, _hvy_to.split(":"))), key=f"sched_ht_{pn}")

            sched_interval = st.number_input("דקות בין סבבים מתוזמנים:", value=int(scheduler_cfg.get("interval_minutes", 5)),
                                              min_value=1, max_value=120, key=f"sched_int_{pn}")
            sched_report = st.text_input("📊 תיקיית דוחות Excel:", value=scheduler_cfg.get("report_folder", ""), key=f"sched_rpt_{pn}")

            if sched_enabled:
                _now = _dt.now().time()
                _in_reg = _is_time_in_range(_now, sched_reg_from, sched_reg_to)
                _in_hvy = _is_time_in_range(_now, sched_hvy_from, sched_hvy_to)
                if _in_reg:
                    st.success(f"⏰ כרגע בטווח ריצה **רגילה** (שעה: {_now.strftime('%H:%M')})")
                elif _in_hvy:
                    st.success(f"⏰ כרגע בטווח ריצה **כבדה** (שעה: {_now.strftime('%H:%M')})")
                else:
                    st.warning(f"⏰ כרגע לא בטווח ריצה (שעה: {_now.strftime('%H:%M')})")

    # ╔════════════════════════════════════════════════╗
    # ║  INNER TAB 4 — LIVE LOG                       ║
    # ╚════════════════════════════════════════════════╝
    with inner_tabs[3]:
        st.subheader(f"📋 לוג — {profile['display_name']}")

        @st.fragment(run_every=5)
        def _log_fragment():
            _bridge = _get_bridge()
            lines = _bridge.get_log_lines(pn, 200)
            if pn == "quotes":
                log_text = read_log_tail(2000, profile_name="quotes")
            elif lines:
                log_text = "\n".join(lines)
            else:
                log_text = "אין הודעות לוג"

            # ── Status (two separate lines) ──
            _rstatus = _bridge.get_run_status(pn)
            _running = _bridge.is_running(pn)
            _sched = _bridge.is_scheduler_active(pn)
            _phase = _rstatus.get("phase", "idle")
            _active = _running or _phase in ("processing", "scanning", "sending")

            # ── Line 1: run status ──
            _run_info = ""
            _rt = _rstatus.get("run_type", "")
            if _rt == "heavy":
                _run_info += " | 🏋️ כבד"
            elif _rt == "regular":
                _run_info += " | 📨 רגיל"
            _ce = _rstatus.get("current_email", 0)
            _te = _rstatus.get("total_emails", 0)
            if _ce and _te:
                _run_info += f" | מייל {_ce}/{_te}"
            elif _te:
                _run_info += f" | {_te} מיילים"
            _phase_labels = {"scanning": "🔍 סורק", "processing": "⚙️ מעבד", "sending": "📤 שולח", "done": "✅ הושלם"}
            _pl = _phase_labels.get(_phase, "")
            if _pl:
                _run_info += f" | {_pl}"

            if _active:
                st.markdown(f'<div class="status-bar"><span class="phase">🟢 פעיל{_run_info}</span></div>', unsafe_allow_html=True)
            elif _run_info:
                st.markdown(f'<div class="status-bar"><span class="phase">⏸ לא פעיל{_run_info}</span></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="status-bar"><span class="phase">⏸ לא פעיל</span></div>', unsafe_allow_html=True)

            # ── Line 2: scheduler / next run (always shown if scheduler active) ──
            if _sched:
                from datetime import datetime as _dt
                _nrt = _bridge.get_next_run_time(pn)
                if _nrt and not _active:
                    _remaining = (_nrt - _dt.now()).total_seconds()
                    if _remaining > 0:
                        _m, _s = divmod(int(_remaining), 60)
                        st.markdown(f'<div class="status-bar"><span class="phase">🕐 מתוזמן | ⏱ סבב הבא בעוד {_m}:{_s:02d}</span></div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="status-bar"><span class="phase">🕐 מתוזמן | ממתין לתחילת סבב</span></div>', unsafe_allow_html=True)
                elif _active:
                    st.markdown(f'<div class="status-bar"><span class="phase">🕐 מתוזמן | סבב רץ כעת</span></div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="status-bar"><span class="phase">🕐 מתוזמן</span></div>', unsafe_allow_html=True)

            st.html(
                f'<div class="log-container" id="logBox_{pn}" style="'
                f'background:#1a1a2e;color:#00ff00;font-family:Consolas,monospace;'
                f'font-size:12px;padding:12px;border-radius:8px;height:450px;'
                f'overflow-y:scroll;direction:ltr;text-align:left;white-space:pre-wrap;'
                f'border:1px solid #FF8C0033;">{log_text}</div>'
                f'<script>var lb=document.getElementById("logBox_{pn}");if(lb)lb.scrollTop=lb.scrollHeight;</script>'
            )

            _log_btns = st.columns([1, 1, 6])
            with _log_btns[0]:
                if st.button("🗑 נקה לוג", key=f"clear_log_{pn}"):
                    # Clear per-profile status_log.txt
                    _profile_log = PROJECT_ROOT / "data" / pn / "status_log.txt"
                    try:
                        if _profile_log.exists():
                            _profile_log.write_text("", encoding="utf-8")
                    except Exception:
                        pass
                    # Clear in-memory lines
                    if pn == "quotes":
                        _qr = st.session_state.get("runner")
                        if _qr and hasattr(_qr, "clear_log"):
                            _qr.clear_log()
                    else:
                        with _bridge._lock:
                            _bridge._log_lines[pn] = []
                    st.rerun()
            with _log_btns[1]:
                if st.button("🔄 רענן", key=f"refresh_log_{pn}"):
                    st.rerun()

        _log_fragment()

    # ═════════════════════════════════════════════════
    # BUTTON HANDLERS — per profile
    # ═════════════════════════════════════════════════

    def _gather_profile_config() -> dict:
        """Collect all widgets into the profile config dict."""
        pm = parse_mailboxes_text(mailboxes_str)
        primary = pm[0] if pm else ""
        fv = sel_folder
        if fv and "(" in fv:
            fv = folder_path_map.get(fv, fv)

        new_cfg = dict(cfg)  # start from existing
        new_cfg["email"] = {
            "shared_mailbox": primary,
            "shared_mailboxes": pm,
            "inbox_folder": fv.strip() if fv else "Inbox",
            "rerun_folder_name": rerun_folder.strip(),
            "rerun_mailbox": rerun_mailbox.strip(),
            "skip_senders": [s.strip().lower() for s in skip_senders.strip().splitlines() if s.strip()],
            "skip_categories": [c.strip() for c in skip_categories.strip().splitlines() if c.strip()],
            "scan_from_date": scan_from.strip(),
            "category_processed": cat_processed.strip(),
            "category_processed_color": _CATEGORY_COLOR_MAP.get(cat_proc_color, "preset20"),
            "category_error": cat_error.strip(),
            "category_error_color": _CATEGORY_COLOR_MAP.get(cat_err_color, "preset1"),
            "category_heavy": email_cfg.get("category_heavy", ""),
            "category_heavy_color": email_cfg.get("category_heavy_color", ""),
            "max_messages_per_cycle": max_msgs,
            "max_files_per_email": max_files,
            "max_file_size_mb": int(email_cfg.get("max_file_size_mb", 100)),
            "scan_interval_minutes": scan_interval,
        }
        new_cfg["folders"] = {
            "download": download_dir.strip(),
            "output": output_dir.strip(),
            "archive": archive_dir.strip(),
            "to_send": tosend_dir.strip(),
        }
        new_cfg["output"] = dict(output_cfg)
        new_cfg["output"]["send_to"] = send_to.strip()
        new_cfg["output"]["send_cc"] = send_cc.strip()
        new_cfg["output"]["auto_send"] = auto_send
        new_cfg["output"]["generate_excel"] = gen_excel
        if b2b_conf is not None:
            new_cfg["output"]["b2b_confidence_level"] = b2b_conf

        new_cfg["processing"] = {
            "recursive": recursive,
            "archive_full": archive_full,
            "cleanup_download": cleanup,
            "mark_as_processed": mark_proc,
            "debug_mode": debug_mode,
        }
        new_cfg["scheduler"] = {
            "enabled": sched_enabled,
            "regular_from": sched_reg_from.strftime("%H:%M"),
            "regular_to": sched_reg_to.strftime("%H:%M"),
            "heavy_from": sched_hvy_from.strftime("%H:%M"),
            "heavy_to": sched_hvy_to.strftime("%H:%M"),
            "interval_minutes": sched_interval,
            "report_folder": sched_report.strip(),
        }

        # AI engine
        new_ai = dict(ai_cfg)
        if engine_type == "vision":
            new_ai["stages"] = [sn for sn in range(10) if stage_enabled.get(sn, False)]
            new_ai["stage_models"] = {str(sn): stage_models.get(sn, "") for sn in range(10) if stage_models.get(sn)}
            if max_img_dim is not None:
                new_ai["max_image_dimension"] = _RESOLUTION_MAP.get(max_img_dim, 4096)
            new_ai["stage1_skip_retry_resolution_px"] = s1_skip
            new_ai["scan_dpi"] = scan_dpi
            new_ai["max_retries"] = max_retries
            new_ai["iai_top_red_fallback"] = iai_top_red
            new_ai["enable_ocr"] = enable_ocr
        else:
            new_ai["di_model"] = di_model
            new_ai["validate_model"] = validate_model
            new_ai["max_retries"] = max_retries
        new_cfg["ai_engine"] = new_ai

        # Validation (DI profiles)
        if engine_type != "vision":
            new_cfg["validation"] = dict(validation_cfg)
            new_cfg["validation"]["use_sql_server"] = use_sql
            new_cfg["validation"]["supplier_lookup"] = supplier_lookup
            new_cfg["validation"]["po_matching"] = po_matching
            new_cfg["validation"]["price_tolerance_percent"] = price_tol
            if review_cfg:
                new_cfg["review"] = dict(review_cfg)
                new_cfg["review"]["enabled"] = review_enabled
                new_cfg["review"]["auto_approve_enabled"] = auto_approve

        return new_cfg

    def _save_quotes_legacy(new_cfg: dict) -> None:
        """Write all relevant fields back to automation_config.json for quotes backward compat."""
        if pn != "quotes":
            return
        _sched = new_cfg.get("scheduler", {})
        save_config(load_config() | {
            "shared_mailbox": new_cfg["email"]["shared_mailbox"],
            "shared_mailboxes": new_cfg["email"]["shared_mailboxes"],
            "folder_name": new_cfg["email"]["inbox_folder"],
            "rerun_folder_name": new_cfg["email"].get("rerun_folder_name", "RERUN"),
            "rerun_mailbox": new_cfg["email"].get("rerun_mailbox", ""),
            "skip_senders": new_cfg["email"].get("skip_senders", []),
            "skip_categories": new_cfg["email"].get("skip_categories", []),
            "scan_from_date": new_cfg["email"].get("scan_from_date", ""),
            "recipient_email": new_cfg["output"].get("send_to", ""),
            "poll_interval_minutes": new_cfg["email"].get("scan_interval_minutes", 5),
            "max_messages": new_cfg["email"].get("max_messages_per_cycle", 700),
            "max_files_per_email": new_cfg["email"].get("max_files_per_email", 12),
            "auto_send": new_cfg["output"].get("auto_send", True),
            "recursive": new_cfg["processing"].get("recursive", True),
            "archive_full": new_cfg["processing"].get("archive_full", False),
            "cleanup_download": new_cfg["processing"].get("cleanup_download", True),
            "mark_as_processed": new_cfg["processing"].get("mark_as_processed", True),
            "mark_category_name": new_cfg["email"].get("category_processed", "AI Processed"),
            "mark_category_color": new_cfg["email"].get("category_processed_color", "preset20"),
            "debug_mode": new_cfg["processing"].get("debug_mode", False),
            "scheduler_enabled": _sched.get("enabled", False),
            "scheduler_regular_from": _sched.get("regular_from", "07:00"),
            "scheduler_regular_to": _sched.get("regular_to", "19:00"),
            "scheduler_heavy_from": _sched.get("heavy_from", "19:00"),
            "scheduler_heavy_to": _sched.get("heavy_to", "07:00"),
            "scheduler_interval_minutes": _sched.get("interval_minutes", 5),
            "scheduler_report_folder": _sched.get("report_folder", ""),
        })

    # ── Save ──
    if save_btn:
        new_cfg = _gather_profile_config()
        save_profile_config(pn, new_cfg)
        _save_quotes_legacy(new_cfg)
        st.toast(f"💾 הגדרות {profile['display_name']} נשמרו!", icon="✅")

    # ── Test connection ──
    if test_btn:
        pm = parse_mailboxes_text(mailboxes_str)
        if not pm:
            st.error("לא הוגדרה אף תיבה לבדיקה")
        else:
            with st.spinner("בודק חיבור לתיבות..."):
                results = test_all_mailboxes(pm)
                ok = [m for m, s in results.items() if s]
                fail = [m for m, s in results.items() if not s]
            if ok:
                st.success(f"✅ תיבות תקינות ({len(ok)}): " + ", ".join(ok))
            if fail:
                st.error(f"❌ תיבות שנכשלו ({len(fail)}): " + ", ".join(fail))

    # ── Run once ──
    if run_btn:
        new_cfg = _gather_profile_config()
        save_profile_config(pn, new_cfg)
        _save_quotes_legacy(new_cfg)
        _bridge = _get_bridge()
        if _bridge.is_running(pn):
            st.toast("⚠️ ריצה כבר פעילה", icon="⚠️")
        elif _bridge.run_once(pn):
            st.toast(f"▶️ מריץ סבב — {profile['display_name']}...", icon="▶️")
        else:
            st.toast("⚠️ ריצה כבר פעילה", icon="⚠️")
        st.rerun()

    # ── Run heavy ──
    if run_heavy_btn:
        new_cfg = _gather_profile_config()
        save_profile_config(pn, new_cfg)
        _save_quotes_legacy(new_cfg)
        _bridge = _get_bridge()
        if _bridge.is_running(pn):
            st.toast("⚠️ ריצה כבר פעילה", icon="⚠️")
        elif _bridge.run_heavy(pn):
            st.toast(f"🏋️ מריץ כבדים — {profile['display_name']}...", icon="🏋️")
        else:
            st.toast("⚠️ ריצה כבר פעילה", icon="⚠️")
        st.rerun()

    # ── Start ──
    if start_btn:
        new_cfg = _gather_profile_config()
        save_profile_config(pn, new_cfg)
        _save_quotes_legacy(new_cfg)
        _bridge = _get_bridge()
        if _bridge.start(pn):
            st.toast(f"🚀 {profile['display_name']} הופעל!", icon="🚀")
        st.rerun()

    # ── Stop (loop + scheduler) ──
    if stop_btn:
        _bridge = _get_bridge()
        _bridge.stop(pn)
        _bridge.stop_scheduler(pn)
        st.toast(f"⏹ {profile['display_name']} נעצר", icon="⏹")
        st.rerun()

    # ── Reset ──
    if reset_btn:
        if st.session_state.get(f"confirm_reset_{pn}", False):
            reset_profile_state(pn)
            if pn == "quotes":
                reset_state()
            st.session_state[f"confirm_reset_{pn}"] = False
            st.toast(f"🔄 State {profile['display_name']} אופס", icon="🔄")
            st.rerun()
        else:
            st.session_state[f"confirm_reset_{pn}"] = True
            st.warning("⚠️ פעולה זו תאפס את המצב — כל המיילים יעובדו מחדש. לחץ שוב לאישור.")
            st.rerun()

    # ── Auto-start/stop scheduler based on checkbox ──
    _bridge_sched = _get_bridge()
    if sched_enabled:
        if not _bridge_sched.is_scheduler_active(pn):
            new_cfg = _gather_profile_config()
            save_profile_config(pn, new_cfg)
            _save_quotes_legacy(new_cfg)
            _bridge_sched.start_scheduler(pn)
    else:
        if _bridge_sched.is_scheduler_active(pn):
            _bridge_sched.stop_scheduler(pn)


# ═══════════════════════════════════════════════════════════════════
# RENDER ALL PROFILE TABS
# ═══════════════════════════════════════════════════════════════════
for _i, _profile in enumerate(profiles):
    with profile_tabs[_i]:
        _render_profile_tab(_profile, _i)
