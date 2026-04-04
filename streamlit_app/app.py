"""
AI GATEWAY KITARON — Streamlit Web UI
Entry point: streamlit run streamlit_app/app.py
"""
import streamlit as st
import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

st.set_page_config(
    page_title="GREEN COAT ALGAT — AI GATEWAY KITARON",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

from streamlit_app.brand import (
    BRAND_CSS, brand_header, sidebar_logo, hero_card,
    ORANGE, GREEN, TEAL, BLUE, TEXT_MUTED, CARD_BG_GLASS, ACCENT_GRADIENT,
)
st.markdown(BRAND_CSS, unsafe_allow_html=True)

# Sidebar
sidebar_logo()

# Branded header
st.html(brand_header("AI GATEWAY KITARON", "מערכת אוטומטית לחילוץ נתונים משרטוטים הנדסיים"))

# Hero navigation cards
col1, col2, col3, col4 = st.columns(4, gap="medium")
with col1:
    st.markdown(hero_card(
        "🚀", "אוטומציה", "הפעלה וניהול",
        color=ORANGE,
        subtitle="ריצה רגילה • כבדה • לולאה"
    ), unsafe_allow_html=True)
    st.page_link("pages/1_🚀_Automation.py", label="פתח אוטומציה →", icon="🚀")
with col2:
    st.markdown(hero_card(
        "📊", "Dashboard", "סטטיסטיקות מלאות",
        color=GREEN,
        subtitle="דיוק • יעילות • עלויות"
    ), unsafe_allow_html=True)
    st.page_link("pages/2_📊_Dashboard.py", label="פתח Dashboard →", icon="📊")
with col3:
    st.markdown(hero_card(
        "📧", "אימייל", "ניהול תיבה משותפת",
        color=TEAL,
        subtitle="חיבור • שליפה • שליחה"
    ), unsafe_allow_html=True)
    st.page_link("pages/3_📧_Email.py", label="פתח אימייל →", icon="📧")
with col4:
    st.markdown(hero_card(
        "📋", "סקירה", "אישור מסמכים DI",
        color=BLUE,
        subtitle="חשבוניות • תעודות קליטה"
    ), unsafe_allow_html=True)
    st.page_link("pages/4_📋_Review.py", label="פתח סקירה →", icon="📋")

st.markdown("")

# Quick status footer
st.markdown(
    f'<div style="text-align:center; padding:20px; color:{TEXT_MUTED}; font-size:12px; '
    f'letter-spacing:1px; text-transform:uppercase;">'
    f'Green Coat Algat &bull; AI GATEWAY KITARON &bull; Powered by AI'
    f'</div>',
    unsafe_allow_html=True,
)
