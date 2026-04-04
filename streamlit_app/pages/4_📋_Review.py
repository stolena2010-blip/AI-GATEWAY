"""
📋 Review — AI GATEWAY KITARON
Document review and approval for DI-based profiles (invoices, delivery notes)
"""
import streamlit as st
import sys
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from streamlit_app.backend.config_manager import load_all_profiles
from streamlit_app.backend.log_reader import load_profile_log_entries
from streamlit_app.brand import BRAND_CSS, brand_header, sidebar_logo

st.set_page_config(page_title="📋 סקירה — AI GATEWAY KITARON", page_icon="🌿", layout="wide")
st.markdown(BRAND_CSS, unsafe_allow_html=True)
sidebar_logo()

st.html(brand_header("סקירה ואישור מסמכים"))

# ── Load profiles with review enabled ──
profiles = load_all_profiles()
review_profiles = [p for p in profiles if p.get("review", {}).get("enabled", False)]

if not review_profiles:
    st.info("אין פרופילים עם סקירה מופעלת. סקירה מוגדרת בפרופילים מסוג Document Intelligence (חשבוניות, תעודות קליטה).")
    st.stop()

# ── Profile selector ──
profile_names = [p["display_name"] for p in review_profiles]
selected_name = st.selectbox("בחר פרופיל:", profile_names)
selected_profile = next(p for p in review_profiles if p["display_name"] == selected_name)
profile_id = selected_profile["profile_name"]

# ── Load pending items ──
st.subheader(f"מסמכים לסקירה — {selected_name}")

entries = load_profile_log_entries(profile_id, max_entries=500)
pending = [e for e in entries if e.get("status") == "pending_review"]
approved = [e for e in entries if e.get("status") == "approved"]

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("ממתינים לסקירה", len(pending))
with col2:
    st.metric("מאושרים", len(approved))
with col3:
    st.metric("סה״כ", len(entries))

if not pending:
    st.success("אין מסמכים ממתינים לסקירה ✅")
else:
    for i, entry in enumerate(pending):
        with st.expander(
            f"📄 {entry.get('file_name', 'מסמך')} — "
            f"{entry.get('supplier_name', '')} — "
            f"₪{entry.get('total_amount', '?')}",
            expanded=(i == 0),
        ):
            # Show extracted data
            display_cols = st.columns(2)
            with display_cols[0]:
                st.write("**פרטי מסמך:**")
                st.json({
                    k: v for k, v in entry.items()
                    if k in (
                        "supplier_name", "supplier_id", "invoice_number",
                        "invoice_date", "total_amount", "vat_amount",
                        "currency", "po_number", "confidence",
                    )
                })
            with display_cols[1]:
                st.write("**ולידציה:**")
                validation_info = {
                    k: v for k, v in entry.items()
                    if k in (
                        "supplier_validated", "po_validated",
                        "price_within_tolerance", "validation_notes",
                    )
                }
                if validation_info:
                    st.json(validation_info)
                else:
                    st.info("לא בוצע ולידציה")

            # Approval buttons
            btn_cols = st.columns(3)
            with btn_cols[0]:
                if st.button("✅ אשר", key=f"approve_{i}"):
                    st.toast(f"מסמך אושר: {entry.get('file_name', '')}", icon="✅")
            with btn_cols[1]:
                if st.button("❌ דחה", key=f"reject_{i}"):
                    st.toast(f"מסמך נדחה: {entry.get('file_name', '')}", icon="❌")
            with btn_cols[2]:
                if st.button("✏️ ערוך", key=f"edit_{i}"):
                    st.toast("עריכה ידנית עדיין לא מיושמת", icon="✏️")
