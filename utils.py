"""
utils.py
UI helpers, CSS injections, theme handling, notification bell, and session
guard rails for TEC TANIVA HRMS.
"""

import streamlit as st
import base64
import os
import hmac
import hashlib
from datetime import datetime
from database import authenticate_user, get_notifications, unread_notification_count, mark_notification_read, mark_all_notifications_read

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

SESSION_SECRET = os.environ.get("HRMS_SESSION_SECRET", "TEC_TANIVA_HRMS_PERSISTENT_KEY_2026")


def _sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def _get_query_param(key, default=None):
    try:
        if hasattr(st, "query_params"):
            return st.query_params.get(key, default)
        params = st.experimental_get_query_params()
        vals = params.get(key, [])
        return vals[0] if vals else default
    except Exception:
        return default


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


# ---------------------------------------------------------------------------
# THEME
# ---------------------------------------------------------------------------

LIGHT_PALETTE = {
    "navy": "#0b1c2c",
    "secondary_navy": "#122a40",
    "teal": "#17b6a7",
    "teal_dark": "#0f8f83",
    "orange": "#f5a623",
    "bg": "#f4f6f9",
    "card": "#ffffff",
    "card_border": "#e2e8f0",
    "text": "#0f172a",
    "muted": "#64748b",
    "input_bg": "#ffffff",
}

DARK_PALETTE = {
    "navy": "#0b1420",
    "secondary_navy": "#101d2b",
    "teal": "#22d3c4",
    "teal_dark": "#17b6a7",
    "orange": "#f5a623",
    "bg": "#0d1520",
    "card": "#141f2e",
    "card_border": "#22334a",
    "text": "#e6edf5",
    "muted": "#93a3b8",
    "input_bg": "#0f1c2b",
}


def get_palette():
    theme = st.session_state.get("ui_theme", "light")
    return DARK_PALETTE if theme == "dark" else LIGHT_PALETTE


PALETTE = LIGHT_PALETTE  # kept for backward-compatible imports; prefer get_palette()


def theme_toggle_control():
    """Small theme switch, meant to be placed in the sidebar."""
    current = st.session_state.get("ui_theme", "light")
    label = "☀️ Switch to Light Mode" if current == "dark" else "🌙 Switch to Dark Mode"
    if st.button(label, use_container_width=True, key="theme_toggle_btn"):
        st.session_state["ui_theme"] = "dark" if current == "light" else "light"
        st.rerun()


def inject_css():
    P = get_palette()
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            color: {P['text']};
        }}

        .stApp {{
            background-color: {P['bg']};
        }}

        #MainMenu, header, footer {{ visibility: hidden; }}

        /* ---------- Sidebar ---------- */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {P['navy']} 0%, {P['secondary_navy']} 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
        }}
        section[data-testid="stSidebar"] * {{
            color: #f1f5f9 !important;
        }}
        section[data-testid="stSidebar"] .stButton > button {{
            background-color: rgba(23, 182, 167, 0.15) !important;
            border: 1px solid {P['teal']} !important;
            color: #ffffff !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            width: 100% !important;
            transition: all 0.15s ease-in-out;
        }}
        section[data-testid="stSidebar"] .stButton > button:hover {{
            background-color: {P['teal']} !important;
            color: {P['navy']} !important;
            border-color: {P['teal']} !important;
            box-shadow: 0 4px 14px rgba(23, 182, 167, 0.35);
        }}

        /* ---------- Main content typography ---------- */
        h1, h2, h3 {{ color: {P['text']} !important; font-weight: 800 !important; letter-spacing: -0.3px; }}
        p, span, label, div {{ color: {P['text']}; }}
        .stCaption, [data-testid="stCaptionContainer"] {{ color: {P['muted']} !important; }}

        /* ---------- Cards ---------- */
        .hr-card {{
            background: {P['card']};
            border-radius: 16px;
            padding: 1.4rem 1.6rem;
            box-shadow: 0 4px 20px -4px rgba(11, 28, 44, 0.08);
            border: 1px solid {P['card_border']};
            margin-bottom: 1.1rem;
        }}
        .hr-card:hover {{ box-shadow: 0 8px 26px -6px rgba(11, 28, 44, 0.14); }}

        .hr-metric {{
            background: linear-gradient(135deg, {P['navy']}, {P['secondary_navy']});
            color: white;
            border-radius: 16px;
            padding: 1.3rem;
            box-shadow: 0 10px 25px -5px rgba(11,28,44,0.20);
            border: 1px solid rgba(255,255,255,0.08);
            text-align: center;
            height: 100%;
        }}
        .hr-metric .label {{
            font-size: 0.72rem;
            color: #93a3b8;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            font-weight: 700;
        }}
        .hr-metric .value {{
            font-size: 1.7rem;
            font-weight: 800;
            color: {P['teal']};
            margin-top: 0.3rem;
            word-break: break-word;
        }}

        /* ---------- Pills / badges ---------- */
        .hr-pill {{
            display: inline-block;
            padding: 0.3rem 0.9rem;
            border-radius: 30px;
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.4px;
            text-transform: uppercase;
            white-space: nowrap;
        }}
        .pill-active {{ background: #dcfce7; color: #166534 !important; }}
        .pill-pending {{ background: #fef9c3; color: #854d0e !important; }}
        .pill-rejected {{ background: #fee2e2; color: #991b1b !important; }}
        .pill-muted {{ background: #e2e8f0; color: #334155 !important; }}

        .hr-badge {{
            display: inline-flex; align-items:center; justify-content:center;
            min-width: 20px; height: 20px; padding: 0 5px;
            border-radius: 10px; background: #ef4444; color: white !important;
            font-size: 0.68rem; font-weight: 700; margin-left: 6px;
        }}

        .hr-avatar {{
            width: 44px; height: 44px; border-radius: 50%;
            background: linear-gradient(135deg, {P['teal']}, {P['teal_dark']});
            color: white !important; display:flex; align-items:center; justify-content:center;
            font-weight: 800; font-size: 1.05rem; flex-shrink: 0;
        }}

        .hr-notif {{
            border-left: 3px solid {P['teal']};
            background: {P['card']};
            border-radius: 10px;
            padding: 0.6rem 0.8rem;
            margin-bottom: 0.5rem;
            font-size: 0.82rem;
        }}
        .hr-notif.unread {{ border-left-color: #ef4444; }}
        .hr-notif .notif-title {{ font-weight: 700; margin-bottom: 2px; }}
        .hr-notif .notif-time {{ font-size: 0.7rem; color: {P['muted']}; margin-top: 3px; }}

        /* ---------- Tabs ---------- */
        button[data-baseweb="tab"] {{
            font-weight: 600 !important;
            border-radius: 10px 10px 0 0 !important;
        }}
        div[data-baseweb="tab-highlight"] {{ background-color: {P['teal']} !important; height: 3px !important; }}

        /* ---------- Buttons (main content) ---------- */
        .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
            border-radius: 10px !important;
            font-weight: 600 !important;
        }}
        .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
            background-color: {P['teal']} !important;
            border-color: {P['teal']} !important;
        }}
        .stButton > button[kind="primary"]:hover {{
            background-color: {P['teal_dark']} !important;
        }}

        /* ---------- Inputs ---------- */
        .stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input, .stSelectbox div[data-baseweb="select"] {{
            background-color: {P['input_bg']} !important;
            color: {P['text']} !important;
        }}

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
            border: 1.5px solid {P['teal']} !important;
            border-radius: 8px !important;
            background-color: transparent !important;
            color: {P['teal_dark']} !important;
            -webkit-text-fill-color: {P['teal_dark']} !important;
        }}
        div[data-baseweb="calendar"] [aria-selected="true"] {{
            background-color: {P['teal']} !important;
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            border-radius: 8px !important;
        }}

        /* ---------- Dataframe polish ---------- */
        [data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; border: 1px solid {P['card_border']}; }}

        /* ---------- Responsive: phones & small tablets ---------- */
        @media (max-width: 768px) {{
            .hr-card {{ padding: 1rem 1.1rem; border-radius: 12px; }}
            .hr-metric {{ padding: 1rem; border-radius: 12px; }}
            .hr-metric .value {{ font-size: 1.35rem; }}
            h1 {{ font-size: 1.5rem !important; }}
            h2 {{ font-size: 1.2rem !important; }}
            .block-container {{ padding-left: 0.8rem !important; padding-right: 0.8rem !important; padding-top: 1rem !important; }}
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
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:0.6rem;">
                    <img src="data:image/png;base64,{logo_b64}" style="height:38px; border-radius:6px; background:white; padding:2px;" />
                    <div>
                        <div style="font-weight:800; font-size:0.95rem; line-height:1.2; color:#ffffff !important;">TEC TANIVA</div>
                        <div style="font-size:0.65rem; color:#94a3b8 !important;">HRMS Portal</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown("### 🏢 TEC TANIVA HRMS")
        st.markdown("---")


def initials(name: str) -> str:
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _format_time(ts):
    if not ts:
        return ""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d %b, %I:%M %p")
    except Exception:
        return str(ts)


def render_notification_bell(recipient_code: str, key_prefix: str = "notif"):
    """Renders a notification bell with unread badge in the sidebar."""
    if not recipient_code:
        return
    unread = unread_notification_count(recipient_code)
    with st.sidebar:
        label = f"🔔 Notifications ({unread} new)" if unread else "🔔 Notifications"
        with st.expander(label, expanded=False):
            notifs = get_notifications(recipient_code, limit=20)
            if not notifs:
                st.caption("You're all caught up — no notifications yet.")
            else:
                if unread and st.button("Mark all as read", key=f"{key_prefix}_mark_all", use_container_width=True):
                    mark_all_notifications_read(recipient_code)
                    st.rerun()
                for n in notifs:
                    cls = "hr-notif unread" if not n["is_read"] else "hr-notif"
                    st.markdown(
                        f"""<div class="{cls}">
                            <div class="notif-title">{n['title']}</div>
                            <div>{n['message']}</div>
                            <div class="notif-time">{_format_time(n['created_at'])}</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )


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
                background-image: linear-gradient(rgba(11, 28, 44, 0.35), rgba(11, 28, 44, 0.35)), url("data:image/png;base64,{bg_b64}");
                background-size: cover; background-position: center; background-repeat: no-repeat; background-attachment: fixed;
            }}
            [data-testid="stForm"] {{
                background: rgba(255, 255, 255, 0.24) !important;
                backdrop-filter: blur(18px) !important;
                -webkit-backdrop-filter: blur(18px) !important;
                border-radius: 20px !important;
                padding: 2rem 2.2rem !important;
                box-shadow: 0 15px 35px rgba(0, 0, 0, 0.25) !important;
                border: 1px solid rgba(255, 255, 255, 0.35) !important;
                max-width: 420px !important;
                margin: 0 auto !important;
            }}
            [data-testid="stForm"] label div p {{
                color: #0f172a !important;
                font-weight: 600 !important;
                font-size: 0.85rem !important;
            }}
            </style>
            """, unsafe_allow_html=True)
    else:
        st.markdown(
            """
            <style>
            .stApp { background: linear-gradient(135deg, #0b1c2c 0%, #17b6a7 140%); }
            [data-testid="stForm"] {
                background: rgba(255, 255, 255, 0.95) !important;
                border-radius: 20px !important;
                padding: 2rem 2.2rem !important;
                box-shadow: 0 15px 35px rgba(0, 0, 0, 0.25) !important;
                max-width: 420px !important;
                margin: 0 auto !important;
            }
            </style>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height: 8vh;'></div>", unsafe_allow_html=True)
    left_spacer, col, right_spacer = st.columns([1, 1.3, 1], gap="large")

    with col:
        portal_title = "Admin / HR Portal" if role == "admin" else "Employee Self-Service Portal"
        with st.form(f"login_form_{role}", clear_on_submit=False):
            logo_b64 = logo_base64()
            logo_html = (f'<img src="data:image/png;base64,{logo_b64}" style="height:44px;border-radius:8px;margin-bottom:8px;" />'
                         if logo_b64 else "🏢")
            st.markdown(
                f"""
                <div style="text-align: center; margin-bottom: 1.2rem;">
                    {logo_html}
                    <h3 style="color: #0f172a; font-weight: 800; margin: 0.3rem 0 0.1rem 0;">TEC TANIVA HRMS</h3>
                    <p style="color: #475569; font-size: 0.85rem; font-weight: 600; margin:0;">{portal_title}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

            username = st.text_input("Username", placeholder="e.g. TT-EMP-0001", autocomplete="username")
            password = st.text_input("Password", type="password", placeholder="Enter password", autocomplete="current-password")

            st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
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
        theme_toggle_control()
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
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
    icon = "⏳"
    if status in ["Active", "Approved"]:
        cls = "pill-active"
        icon = "✅"
    elif status in ["Rejected", "Terminated", "Inactive"]:
        cls = "pill-rejected"
        icon = "❌"
    return f'<span class="hr-pill {cls}">{icon} {status}</span>'