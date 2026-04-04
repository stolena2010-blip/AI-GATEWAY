"""
📧 Email — AI GATEWAY KITARON
Per-profile email management: test connections, browse folders
Each document type has its own tab with its own mailbox settings.
"""
import streamlit as st
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from streamlit_app.backend.config_manager import (
    load_all_profiles, load_profile_config, save_profile_config,
)
from streamlit_app.backend.email_helpers import (
    parse_mailboxes_text,
    test_mailbox_connection,
    test_all_mailboxes,
    load_folders_for_mailbox,
    format_folder_label,
)
from streamlit_app.brand import BRAND_CSS, brand_header, sidebar_logo, profile_banner, profile_tab_css

st.set_page_config(page_title="📧 Email — AI GATEWAY KITARON", page_icon="🌿", layout="wide")

st.markdown(BRAND_CSS, unsafe_allow_html=True)
sidebar_logo()
st.html(brand_header("אימייל — AI GATEWAY KITARON"))
st.html(profile_tab_css())

_PROFILE_ICONS = {
    "quotes": "📐", "orders": "📦", "invoices": "🧾",
    "delivery": "🚚", "complaints": "📣",
}

profiles = load_all_profiles()
if not profiles:
    st.warning("לא נמצאו פרופילים בתיקיית configs/")
    st.stop()

# Per-profile session state
for _p in profiles:
    _pn = _p["profile_name"]
    if f"email_folders_{_pn}" not in st.session_state:
        st.session_state[f"email_folders_{_pn}"] = []

tab_labels = [f'{_PROFILE_ICONS.get(p["profile_name"], "📄")} {p["display_name"]}' for p in profiles]
tabs = st.tabs(tab_labels)

for i, profile in enumerate(profiles):
    with tabs[i]:
        pn = profile["profile_name"]
        st.html(profile_banner(pn))
        cfg = load_profile_config(pn)
        if not cfg:
            st.error(f"לא נמצא קובץ הגדרות עבור {pn}")
            continue

        email_cfg = cfg.get("email", {})

        st.subheader(f"📧 {profile['display_name']} — הגדרות מייל")

        mailboxes_str = st.text_input(
            "תיבות משותפות (מופרדות בפסיק):",
            value=", ".join(email_cfg.get("shared_mailboxes", [])) or email_cfg.get("shared_mailbox", ""),
            key=f"email_mbox_{pn}",
        )
        parsed = parse_mailboxes_text(mailboxes_str)

        inbox_folder = st.text_input(
            "תיקיית דואר נכנס:", value=email_cfg.get("inbox_folder", "Inbox"),
            key=f"email_inbox_{pn}",
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔌 בדוק חיבור", key=f"email_test_{pn}", width="stretch"):
                if parsed:
                    with st.spinner("בודק חיבור..."):
                        results = test_all_mailboxes(parsed)
                        ok = [m for m, s in results.items() if s]
                        fail = [m for m, s in results.items() if not s]
                    if ok:
                        st.success(f"✅ תקינות: {', '.join(ok)}")
                    if fail:
                        st.error(f"❌ נכשלו: {', '.join(fail)}")
                else:
                    st.warning("הזן כתובת תיבה")

        with col2:
            sel_mbox = parsed[0] if parsed else ""
            if st.button("📂 טען תיקיות", key=f"email_load_{pn}", width="stretch"):
                if sel_mbox:
                    with st.spinner("טוען תיקיות..."):
                        folders, err = load_folders_for_mailbox(sel_mbox)
                    if err:
                        st.error(err)
                    else:
                        st.session_state[f"email_folders_{pn}"] = folders
                        st.success(f"נטענו {len(folders)} תיקיות")
                else:
                    st.warning("הזן כתובת תיבה")

        with col3:
            if st.button("💾 שמור", key=f"email_save_{pn}", width="stretch"):
                primary = parsed[0] if parsed else ""
                cfg["email"]["shared_mailbox"] = primary
                cfg["email"]["shared_mailboxes"] = parsed
                cfg["email"]["inbox_folder"] = inbox_folder.strip()
                save_profile_config(pn, cfg)
                st.toast(f"💾 הגדרות מייל {profile['display_name']} נשמרו!", icon="✅")

        # Show folders
        loaded = st.session_state.get(f"email_folders_{pn}", [])
        if loaded:
            st.subheader("📁 תיקיות")
            folder_data = []
            for f in loaded:
                folder_data.append({
                    "נתיב": f["path"],
                    "פריטים": f.get("totalItemCount", "—"),
                })
            st.dataframe(folder_data, use_container_width=True)
