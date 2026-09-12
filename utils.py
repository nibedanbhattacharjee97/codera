"""
utils.py
UI helpers, CSS injections, background theme wrappers, and session guard rails
for TEC TANIVA HRMS.
"""

import streamlit as st
import base64
import os
from database import authenticate_user

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

def get_base64_image(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

def logo_base64():
    return get_base64_image(os.path.join(ASSETS_DIR, "logo.png"))

PALETTE = {
    "navy": "#0b1c2c",
    "secondary_navy": "#122a40",
    "teal": "#17b6a7",
    "teal_dark": "#0f8f83",
    "orange": "#f5a623",
    "bg": "#f8fafc",
    "card": "#ffffff",
    "text": "#0f172a",
    "muted": "#64748b",
}

def inject_css():
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            color: {PALETTE['text']};
        }}

        .stApp {{
            background-color: {PALETTE['bg']};
        }}

        #MainMenu, header, footer {{ visibility: hidden; }}

        /* ---------- Sidebar High Contrast Styling ---------- */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {PALETTE['navy']} 0%, {PALETTE['secondary_navy']} 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
        }}
        section[data-testid="stSidebar"] * {{
            color: #ffffff !important;
        }}
        
        /* Force Sidebar Buttons to be Highly Visible */
        section[data-testid="stSidebar"] .stButton > button {{
            background-color: rgba(23, 182, 167, 0.15) !important;
            border: 1px solid {PALETTE['teal']} !important;
            color: #ffffff !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            width: 100% !important;
            transition: all 0.2s ease-in-out;
        }}
        section[data-testid="stSidebar"] .stButton > button:hover {{
            background-color: {PALETTE['teal']} !important;
            color: {PALETTE['navy']} !important;
            border-color: {PALETTE['teal']} !important;
            box-shadow: 0 4px 12px rgba(23, 182, 167, 0.3);
        }}

        /* Modern Enterprise Cards */
        .hr-card {{
            background: {PALETTE['card']};
            border-radius: 16px;
            padding: 1.5rem 1.8rem;
            box-shadow: 0 4px 20px -2px rgba(11, 28, 44, 0.05);
            border: 1px solid #e2e8f0;
            margin-bottom: 1.2rem;
        }}

        /* Metric Cards */
        .hr-metric {{
            background: linear-gradient(135deg, {PALETTE['navy']}, {PALETTE['secondary_navy']});
            color: white;
            border-radius: 16px;
            padding: 1.4rem;
            box-shadow: 0 10px 25px -5px rgba(11,28,44,0.15);
            border: 1px solid rgba(255,255,255,0.1);
            text-align: center;
        }}
        .hr-metric .label {{
            font-size: 0.75rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            font-weight: 600;
        }}
        .hr-metric .value {{
            font-size: 1.8rem;
            font-weight: 700;
            color: {PALETTE['teal']};
            margin-top: 0.3rem;
        }}

        /* Badges & Pills */
        .hr-pill {{
            display: inline-block;
            padding: 0.3rem 0.9rem;
            border-radius: 30px;
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
        .pill-active {{ background: #dcfce7; color: #166534 !important; }}
        .pill-pending {{ background: #fef9c3; color: #854d0e !important; }}
        .pill-rejected {{ background: #fee2e2; color: #991b1b !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_sidebar_brand():
    logo_b64 = logo_base64()
    with st.sidebar:
        if logo_b64:
            st.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:1rem;">
                    <img src="data:image/png;base64,{logo_b64}" style="height:38px; border-radius:6px; background:white; padding:2px;" />
                    <div>
                        <div style="font-weight:700; font-size:0.95rem; line-height:1.2; color:#ffffff;">TEC TANIVA</div>
                        <div style="font-size:0.65rem; color:#94a3b8 !important;">HRMS Portal</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown("### 🏢 TEC TANIVA HRMS")
        st.markdown("---")

def require_login(role="admin"):
    if "authenticated" not in st.session_state or not st.session_state["authenticated"]:
        bg_filename = "admin_bg.png" if role == "admin" else "employee_bg.png"
        bg_path = os.path.join(ASSETS_DIR, bg_filename)
        bg_b64 = get_base64_image(bg_path)
        
        if bg_b64:
            st.markdown(
                f"""
                <style>
                .stApp {{
                    background-image: linear-gradient(rgba(11, 28, 44, 0.15), rgba(11, 28, 44, 0.15)), url("data:image/png;base64,{bg_b64}");
                    background-size: cover;
                    background-position: center;
                    background-repeat: no-repeat;
                    background-attachment: fixed;
                }}
                /* Completely remove Streamlit form background box, borders, and extra padding */
                [data-testid="stForm"] {{
                    background: rgba(255, 255, 255, 0.95) !important;
                    backdrop-filter: blur(12px) !important;
                    border-radius: 20px !important;
                    padding: 2rem 2rem !important;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.25) !important;
                    border: 1px solid rgba(255, 255, 255, 0.9) !important;
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height: 8vh;'></div>", unsafe_allow_html=True)
        col_left, col_right = st.columns([1.25, 1.05])
        
        with col_right:
            with st.form("login_form", clear_on_submit=False):
                username = st.text_input("Username", placeholder="Enter username")
                password = st.text_input("Password", type="password", placeholder="••••••••")
                st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                submitted = st.form_submit_button("Sign In to Portal", use_container_width=True)
                
                if submitted:
                    user = authenticate_user(username, password)
                    if user and user["role"] == role:
                        st.session_state["authenticated"] = True
                        st.session_state["username"] = user["username"]
                        st.session_state["role"] = user["role"]
                        st.session_state["employee_code"] = user["employee_code"]
                        st.rerun()
                    else:
                        st.error("Invalid credentials or unauthorized portal access.")
        st.stop()
        
    elif st.session_state.get("role") != role:
        st.warning(f"Active session mismatch: Logged in as {st.session_state.get('role')}. Please sign out first.")
        if st.button("Sign Out"):
            st.session_state.clear()
            st.rerun()
        st.stop()

def logout_button():
    with st.sidebar:
        st.markdown("---")
        if st.button("🚪 Sign Out", use_container_width=True):
            st.session_state.clear()
            st.rerun()

def metric_card(label, value):
    st.markdown(
        f"""
        <div class="hr-metric">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def status_pill(status):
    cls = "pill-pending"
    if status in ["Active", "Approved"]:
        cls = "pill-active"
    elif status in ["Rejected", "Terminated", "Inactive"]:
        cls = "pill-rejected"
    return f'<span class="hr-pill {cls}">{status}</span>'