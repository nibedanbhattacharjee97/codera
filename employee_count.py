"""
employee.py
Employee Self-Service Portal for viewing profiles, tracking leave balances,
applying for time-off, and downloading uploaded records.
"""

import os
import streamlit as st
from datetime import date

from database import (
    init_db, get_employee, get_leave_balance, apply_leave, get_leave_requests,
    change_password, get_announcements,
)
from utils import (
    inject_css, render_sidebar_brand, require_login, logout_button,
    metric_card, status_pill, PALETTE,
)

st.set_page_config(page_title="Employee Portal | TEC TANIVA HRMS", page_icon="👤", layout="wide")
init_db()
inject_css()
require_login(role="employee")

emp_code = st.session_state.get("employee_code")

if not emp_code:
    st.error("Session employee code missing. Please sign out and log back in.")
    st.stop()

emp = get_employee(emp_code)

if not emp:
    st.error(f"Employee profile record not found for code: {emp_code}. Please contact HR.")
    st.stop()

render_sidebar_brand()
with st.sidebar:
    if emp.get("pic_path") and os.path.exists(emp["pic_path"]):
        st.image(emp["pic_path"], width=90)
    st.markdown(f"**{emp['employee_name']}** \n{emp.get('designation') or 'Employee'}")
    st.markdown('<span class="hr-pill pill-active">EMPLOYEE PORTAL</span>', unsafe_allow_html=True)
logout_button()

st.title(f"Welcome, {emp['employee_name'].split(' ')[0]} 👋")
st.caption("Your self-service portal — profile, leave balances, salary details, and company updates.")

bal = get_leave_balance(emp_code)
casual_left = bal["casual_total"] - bal["casual_used"]
sick_left = bal["sick_total"] - bal["sick_used"]
earned_left = bal["earned_total"] - bal["earned_used"]

c1, c2, c3, c4 = st.columns(4)
with c1: metric_card("Casual Leave Left", f"{casual_left:g} / {bal['casual_total']:g}")
with c2: metric_card("Sick Leave Left", f"{sick_left:g} / {bal['sick_total']:g}")
with c3: metric_card("Earned Leave Left", f"{earned_left:g} / {bal['earned_total']:g}")
with c4: metric_card("Monthly CTC", f"₹ {emp.get('ctc', 0):,.0f}")

st.write("")
tab_profile, tab_payslip, tab_leave, tab_docs, tab_news, tab_settings = st.tabs(
    ["🧾 My Profile", "💰 Salary Structure", "🗓️ Leave Application", "📁 My Documents", "📢 Announcements", "⚙️ Settings"]
)

with tab_profile:
    st.markdown('<div class="hr-card">', unsafe_allow_html=True)
    p1, p2 = st.columns([1, 2])
    with p1:
        if emp.get("pic_path") and os.path.exists(emp["pic_path"]):
            st.image(emp["pic_path"], width=180)
        else:
            st.markdown("*(No profile photo uploaded)*")
        st.markdown(status_pill(emp.get("status", "Active")), unsafe_allow_html=True)
    with p2:
        st.markdown(f"### {emp['employee_name']}")
        st.caption(f"{emp.get('designation') or 'Employee'} · {emp['employee_code']}")
        colx, coly = st.columns(2)
        with colx:
            st.write(f"**Date of Birth:** {emp.get('dob') or '—'}")
            st.write(f"**Date of Joining:** {emp.get('date_of_joining') or '—'}")
            st.write(f"**Qualification:** {emp.get('highest_qualification') or '—'}")
            st.write(f"**Employee Type:** {emp.get('employee_type') or '—'}")
        with coly:
            st.write(f"**Reporting Boss:** {emp.get('reporting_boss') or '—'}")
            st.write(f"**Mobile:** {emp.get('mobile_number') or '—'}")
            st.write(f"**Email:** {emp.get('email') or '—'}")
            st.write(f"**Place:** {emp.get('place') or '—'}")
        st.write(f"**Emergency Contact:** {emp.get('emergency_contact_number') or '—'}")
        st.write(f"**UAN:** {emp.get('uan_number') or '—'} &nbsp;·&nbsp; **ESIC No.:** {emp.get('esic_number') or '—'}")
    st.markdown("</div>", unsafe_allow_html=True)

with tab_payslip:
    st.subheader("Salary & Compensation Summary")
    st.markdown('<div class="hr-card">', unsafe_allow_html=True)
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Basic Pay", f"₹{emp.get('basic_pay', 0):,.0f}")
    s2.metric("DA", f"₹{emp.get('da', 0):,.0f}")
    s3.metric("HRA", f"₹{emp.get('hra', 0):,.0f}")
    s4.metric("Phone Bill", f"₹{emp.get('phonebill_pay', 0):,.0f}")
    s5.metric("Others", f"₹{emp.get('others', 0):,.0f}")

    st.markdown("---")
    st.markdown("##### Deductions (from your gross pay)")
    esic_applicable = emp.get("esic_if_applicable", "No") == "Yes" and emp.get("esic_eligible_by_wage")
    d1, d2 = st.columns(2)
    d1.metric("Employee PF", f"₹{emp.get('pf', 0):,.0f}")
    d2.metric("Employee ESIC (0.75%)", f"₹{emp.get('employee_esic', 0):,.0f}" if esic_applicable else "Not Applicable")

    st.markdown("---")
    st.markdown("##### Employer Contributions (paid on top of your gross, part of CTC)")
    e1, e2, e3 = st.columns(3)
    e1.metric("Employer PF (EPF+EPS+EDLI+Admin)", f"₹{emp.get('employer_pf_total', 0):,.0f}")
    e2.metric("Employer ESIC (3.25%)", f"₹{emp.get('employer_esic', 0):,.0f}" if esic_applicable else "Not Applicable")
    e3.metric("ESIC Status", "Eligible" if esic_applicable else "Not Applicable")

    pf_basis = emp.get("pf_basis") or "capped"
    pf_basis_display = "Actual / Full Basic+DA (voluntary higher PF)" if pf_basis == "actual" else "Statutory Ceiling (₹15,000 cap)"
    esic_ceiling_display = f"₹{emp.get('esic_wage_ceiling_used', 21000):,.0f}" + (" (PwD ceiling)" if emp.get("is_pwd") else "")

    st.caption(f"PF Contribution Basis: **{pf_basis_display}** &nbsp;·&nbsp; ESIC Wage Ceiling Applied: **{esic_ceiling_display}**")

    st.markdown("---")
    note = " (includes statutory ESIC employer contribution)" if esic_applicable else ""
    st.markdown(
        f"""
        <div class="hr-metric">
            <div class="label">Total Monthly CTC{note}</div>
            <div class="value">₹ {emp.get('ctc', 0):,.2f}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

with tab_leave:
    st.subheader("Apply for Leave")
    st.markdown('<div class="hr-card">', unsafe_allow_html=True)
    with st.form("leave_form"):
        lc1, lc2, lc3 = st.columns(3)
        with lc1: leave_type = st.selectbox("Leave Type", ["Casual", "Sick", "Earned"])
        with lc2: from_d = st.date_input("From Date", value=date.today())
        with lc3: to_d = st.date_input("To Date", value=date.today())
        reason = st.text_area("Reason for Leave")
        apply = st.form_submit_button("Submit Leave Request", use_container_width=True)
        if apply:
            if to_d < from_d:
                st.error("'To' date cannot precede 'From' date.")
            else:
                days = (to_d - from_d).days + 1
                apply_leave(emp_code, leave_type, from_d, to_d, days, reason)
                st.success(f"Leave request for {days} day(s) submitted successfully.")
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("My Leave History")
    my_reqs = get_leave_requests(emp_code)
    if not my_reqs:
        st.info("No leave requests submitted.")
    else:
        for r in my_reqs:
            st.markdown(
                f"""<div class="hr-card" style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <b>{r['leave_type']} Leave</b> · {r['from_date']} to {r['to_date']} ({r['days']} day(s))<br>
                    <span style="color:{PALETTE['muted']};font-size:0.8rem;">Applied on {r['applied_on']}</span>
                </div>
                <div>{status_pill(r['status'])}</div>
                </div>""",
                unsafe_allow_html=True,
            )

with tab_docs:
    st.subheader("My Uploaded Documents")
    doc_fields = [
        ("ID Card", "id_card_path"), ("Certificate", "certificate_path"),
        ("CV / Resume", "cv_path"), ("Extra Document 1", "extra_doc1_path"),
        ("Extra Document 2", "extra_doc2_path"), ("Extra Document 3", "extra_doc3_path"),
        ("Extra Document 4", "extra_doc4_path"),
    ]
    cols = st.columns(3)
    i = 0
    for label, field in doc_fields:
        path = emp.get(field)
        with cols[i % 3]:
            st.markdown('<div class="hr-card">', unsafe_allow_html=True)
            st.write(f"**{label}**")
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    st.download_button("⬇️ Download Document", f, file_name=os.path.basename(path), key=f"emp_dl_{field}")
            else:
                st.caption("Not uploaded")
            st.markdown("</div>", unsafe_allow_html=True)
        i += 1

with tab_news:
    st.subheader("Company Announcements")
    anns = get_announcements(10)
    if not anns:
        st.info("No active announcements.")
    for a in anns:
        st.markdown(
            f"""<div class="hr-card"><b>{a['title']}</b>
            <p style="color:{PALETTE['muted']};margin:4px 0;">{a['message'] or ''}</p>
            <span style="color:{PALETTE['muted']};font-size:0.75rem;">{a['created_at']}</span></div>""",
            unsafe_allow_html=True,
        )

with tab_settings:
    st.subheader("Account Settings")
    with st.form("pw_form"):
        new_pw = st.text_input("New Password", type="password")
        confirm_pw = st.text_input("Confirm New Password", type="password")
        change = st.form_submit_button("Update Password", use_container_width=True)
        if change:
            if not new_pw or len(new_pw) < 6:
                st.error("Password must be at least 6 characters.")
            elif new_pw != confirm_pw:
                st.error("Passwords do not match.")
            else:
                change_password(st.session_state["username"], new_pw)
                st.success("Password updated successfully.")