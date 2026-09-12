"""UI, authentication and styling helpers for TEC TANIVA HRMS."""
from __future__ import annotations
import base64, os, time
import streamlit as st
from database import authenticate_user

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
SESSION_TIMEOUT_SECONDS = int(os.getenv("HRMS_SESSION_TIMEOUT", "28800"))

PALETTE={"navy":"#0b1c2c","secondary_navy":"#122a40","teal":"#17b6a7","teal_dark":"#0f8f83","orange":"#f5a623","bg":"#f8fafc","card":"#ffffff","text":"#0f172a","muted":"#64748b"}


def get_base64_image(path):
    try:
        with open(path,"rb") as f: return base64.b64encode(f.read()).decode()
    except (OSError,TypeError): return ""


def logo_base64(): return get_base64_image(os.path.join(ASSETS_DIR,"logo.png"))


def inject_css():
    st.markdown(f"""<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
    html,body,[class*="css"]{{font-family:'Plus Jakarta Sans',sans-serif;color:{PALETTE['text']}}}
    .stApp{{background:{PALETTE['bg']}}} #MainMenu,footer{{visibility:hidden}}
    section[data-testid="stSidebar"]{{background:linear-gradient(180deg,{PALETTE['navy']},{PALETTE['secondary_navy']});border-right:1px solid rgba(255,255,255,.08)}}
    section[data-testid="stSidebar"] *{{color:#fff!important}}
    .hr-card{{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:1.4rem 1.6rem;margin-bottom:1rem;box-shadow:0 5px 22px rgba(11,28,44,.05)}}
    .hr-metric{{background:linear-gradient(135deg,{PALETTE['navy']},{PALETTE['secondary_navy']});color:#fff;border-radius:16px;padding:1.2rem;box-shadow:0 10px 25px rgba(11,28,44,.12);text-align:center}}
    .hr-metric .label{{font-size:.72rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.7px;font-weight:700}} .hr-metric .value{{font-size:1.7rem;font-weight:700;color:{PALETTE['teal']};margin-top:.25rem}}
    .hr-pill{{display:inline-block;padding:.3rem .8rem;border-radius:30px;font-size:.7rem;font-weight:700;text-transform:uppercase}} .pill-active{{background:#dcfce7;color:#166534!important}} .pill-pending{{background:#fef9c3;color:#854d0e!important}} .pill-rejected{{background:#fee2e2;color:#991b1b!important}}
    div[data-baseweb="popover"],div[data-baseweb="calendar"]{{background:#fff!important;color:#0f172a!important;border-radius:12px!important;box-shadow:0 10px 25px rgba(0,0,0,.15)!important}}
    div[data-baseweb="calendar"] *{{color:#0f172a!important;-webkit-text-fill-color:#0f172a!important}}
    .login-card{{max-width:520px;margin:6vh auto 0;background:rgba(255,255,255,.97);border:1px solid rgba(255,255,255,.9);border-radius:24px;padding:2rem;box-shadow:0 20px 50px rgba(0,0,0,.22)}}
    .login-brand{{text-align:center;margin-bottom:1.5rem}} .login-brand h1{{margin:.4rem 0 .2rem;font-size:1.7rem}} .login-brand p{{color:{PALETTE['muted']};margin:0}}
    [data-testid="stForm"]{{border-radius:16px}}
    </style>""",unsafe_allow_html=True)


def render_sidebar_brand():
    with st.sidebar:
        logo=logo_base64()
        if logo: st.markdown(f'<div style="display:flex;gap:10px;align-items:center;margin-bottom:12px"><img src="data:image/png;base64,{logo}" style="height:38px;border-radius:6px;background:white;padding:2px"><div><b>TEC TANIVA</b><div style="font-size:.65rem;color:#94a3b8!important">HRMS Portal</div></div></div>',unsafe_allow_html=True)
        else: st.markdown("### 🏢 TEC TANIVA HRMS")
        st.markdown("---")


def _logout():
    for k in list(st.session_state.keys()): del st.session_state[k]
    st.rerun()


def require_login(role="admin"):
    if st.session_state.get("authenticated"):
        if st.session_state.get("role") != role:
            st.error("This session belongs to another portal. Please sign out and sign in again.")
            if st.button("Sign Out", type="primary"): _logout()
            st.stop()
        last=st.session_state.get("last_activity",time.time())
        if time.time()-last>SESSION_TIMEOUT_SECONDS:
            _logout()
        st.session_state["last_activity"]=time.time()
        return

    bg=get_base64_image(os.path.join(ASSETS_DIR,"admin_bg.png" if role=="admin" else "employee_bg.png"))
    if bg:
        st.markdown(f'<style>.stApp{{background-image:linear-gradient(rgba(11,28,44,.18),rgba(11,28,44,.18)),url("data:image/png;base64,{bg}");background-size:cover;background-position:center;background-attachment:fixed}}</style>',unsafe_allow_html=True)
    st.markdown('<div class="login-card"><div class="login-brand"><div style="font-size:2.2rem">🔐</div><h1>TEC TANIVA HRMS</h1><p>Secure Employee Portal Access</p></div>',unsafe_allow_html=True)
    with st.form(f"login_form_{role}"):
        username=st.text_input("Username",placeholder="Enter your portal username",autocomplete="username")
        password=st.text_input("Password",type="password",placeholder="Enter your password",autocomplete="current-password")
        submitted=st.form_submit_button("Sign In",type="primary",use_container_width=True)
        if submitted:
            if not username.strip() or not password:
                st.error("Please enter both username and password.")
            else:
                user=authenticate_user(username,password)
                if user is None:
                    st.error("Invalid username or password. Check the credentials and try again.")
                elif user.get("role") != role:
                    st.error("This account is not authorized for this portal.")
                elif role == "employee" and not user.get("employee_code"):
                    st.error("This employee account is not linked to an employee record. Contact HR/Admin.")
                else:
                    st.session_state.update(
                        authenticated=True,
                        username=user["username"],
                        role=user["role"],
                        employee_code=user.get("employee_code"),
                        last_activity=time.time(),
                    )
                    st.rerun()
    st.markdown('<div style="text-align:center;color:#64748b;font-size:.8rem;margin-top:12px">If you cannot sign in, contact HR/Admin to reset your portal password.</div></div>',unsafe_allow_html=True)
    st.stop()


def logout_button():
    with st.sidebar:
        st.markdown("---")
        if st.button("🚪 Sign Out",use_container_width=True): _logout()


def metric_card(label,value): st.markdown(f'<div class="hr-metric"><div class="label">{label}</div><div class="value">{value}</div></div>',unsafe_allow_html=True)


def status_pill(status):
    status=status or "Unknown"; cls="pill-pending"
    if status in {"Active","Approved"}: cls="pill-active"
    elif status in {"Rejected","Terminated","Inactive"}: cls="pill-rejected"
    return f'<span class="hr-pill {cls}">{status}</span>'
