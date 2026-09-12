"""
utils.py
UI helpers, CSS injections, background theme wrappers, and session guard rails
for TEC TANIVA HRMS.
"""

import streamlit as st
import base64
import os
import hmac
import hashlib
from database import authenticate_user

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

SESSION_SECRET = os.environ.get("HRMS_SESSION_SECRET", "TEC_TANIVA_HRMS_PERSISTENT_KEY_2026")


def _sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def _make_token(username, role, employee_code):
    emp = str(employee_code or "")
    payload = f"{username}:{role}:{emp}"
    sig = _sign(payload)
    data = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(data.encode()).decode()


def _verify_token(token):
    try:
        data = base64.urlsafe_b64decode(token.encode()).decode()
        parts = data.split(":")
        if len(parts) != 4:
            return None
        username, role, emp, sig = parts
        payload = f"{username}:{role}:{emp}"
        expected_sig = _sign(payload)
        if hmac.compare_digest(sig, expected_sig):
            return {"username": username, "role": role, "employee_code": emp}
    except Exception:
        pass
    return None


def _get_query_param(key, default=None):
    try:
        if hasattr(st, "query_params"):
            return st.query_params.get(key, default)
        params = st.experimental_get_query_params()
        vals = params.get(key, [])
        return vals[0] if vals else default
    except Exception:
        return default


def _set_query_param(key, value):
    try:
        if hasattr(st, "query_params"):
            st.query_params[key] = value
        else:
            params = st.experimental_get_query_params()
            params[key] = value
            st.experimental_set_query_params(**params)
    except Exception:
        pass


def _clear_query_params():
    try:
        if hasattr(st, "query_params"):
            st.query_params.clear()
        else:
            st.experimental_set_query_params()
    except Exception:
        pass


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

        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {PALETTE['navy']} 0%, {PALETTE['secondary_navy']} 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
        }}
        section[data-testid="stSidebar"] * {{
            color: #ffffff !important;
        }}

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

        .hr-card {{
            background: {PALETTE['card']};
            border-radius: 16px;
            padding: 1.5rem 1.8rem;
            box-shadow: 0 4px 20px -2px rgba(11, 28, 44, 0.05);
            border: 1px solid #e2e8f0;
            margin-bottom: 1.2rem;
        }}

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

        div[data-baseweb="popover"], div[data-baseweb="calendar"] {{
            background-color: #ffffff !important;
            color: #0f172a !important;
            box-shadow: 0 10px 25px rgba(0,0,0,0.15) !important;
            border-radius: 12px !important;
        }}
        div[data-baseweb="calendar"] div, div[data-baseweb="calendar"] span, div[data-baseweb="calendar"] button {{
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
        }}
        div[data-baseweb="calendar"] button:hover {{
            background-color: #f1f5f9 !important;
            color: #0f172a !important;
        }}
        div[data-baseweb="calendar"] [aria-label*="Today"]:not([aria-selected="true"]) {{
            border: 1.5px solid {PALETTE['teal']} !important;
            border-radius: 8px !important;
            background-color: transparent !important;
            color: {PALETTE['teal_dark']} !important;
            -webkit-text-fill-color: {PALETTE['teal_dark']} !important;
        }}
        div[data-baseweb="calendar"] [aria-selected="true"] {{
            background-color: {PALETTE['teal']} !important;
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            border-radius: 8px !important;
        }}
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
    """Strict session-only authentication. No auth tokens are accepted from URLs."""
    current_role = st.session_state.get("role")
    authenticated = bool(st.session_state.get("authenticated"))

    if authenticated and current_role == role:
        return

    if authenticated and current_role != role:
        st.warning(f"You are already signed in as {current_role}. Please sign out before opening this portal.")
        if st.button("Sign Out"):
            st.session_state.clear()
            st.rerun()
        st.stop()

    bg_filename = "admin_bg.png" if role == "admin" else "employee_bg.png"
    bg_path = os.path.join(ASSETS_DIR, bg_filename)
    bg_b64 = get_base64_image(bg_path)

    if bg_b64:
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-image: linear-gradient(rgba(11, 28, 44, 0.15), rgba(11, 28, 44, 0.15)), url("data:image/png;base64,{bg_b64}");
                background-size: cover; background-position: center; background-repeat: no-repeat; background-attachment: fixed;
            }}
            [data-testid="stForm"] {{
                background: rgba(255,255,255,0.95) !important; backdrop-filter: blur(12px) !important;
                border-radius: 20px !important; padding: 2rem !important; box-shadow: 0 15px 35px rgba(0,0,0,0.25) !important;
                border: 1px solid rgba(255,255,255,0.9) !important;
            }}
            </style>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height: 8vh;'></div>", unsafe_allow_html=True)
    _, col = st.columns([1.0, 1.25])
    with col:
        st.markdown(f"## {'Admin' if role == 'admin' else 'Employee'} Portal Login")
        st.caption("")
        with st.form(f"login_form_{role}", clear_on_submit=False):
            username = st.text_input("Username", placeholder="e.g. TT-EMP-0001", autocomplete="username")
            password = st.text_input("Password", type="password", placeholder="Enter password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")
            if submitted:
                user = authenticate_user(username, password)
                if user and user.get("role") == role:
                    if role == "employee" and not user.get("employee_code"):
                        st.error("This employee login is not linked to an employee record. Please contact HR/Admin.")
                        st.stop()
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = user["username"]
                    st.session_state["role"] = user["role"]
                    st.session_state["employee_code"] = user.get("employee_code")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
    st.stop()


def logout_button():
    with st.sidebar:
        st.markdown("---")
        if st.button("🚪 Sign Out", use_container_width=True):
            _clear_query_params()
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