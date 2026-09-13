"""
employee.py
Employee Self-Service Portal for viewing profiles, tracking leave balances,
applying for time-off, approving team leave (for reporting managers),
downloading payslips, and viewing uploaded documents.
"""

import os
from datetime import date

import streamlit as st

from database import (
    init_db, get_employee, apply_leave, get_leave_requests,
    change_password, get_announcements, LEAVE_TYPES, LEAVE_TYPE_LABELS,
    get_leave_balance_map, get_employees_reporting_to, decide_leave,
    get_payroll_months_for_employee, get_payroll_record, MONTH_NAMES,
)
from utils import (
    inject_css, render_sidebar_brand, require_login, logout_button,
    metric_card, status_pill, render_notification_bell, initials,
)
from payslip import generate_payslip_pdf

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

is_permanent = emp.get("employee_type") == "Permanent"
team_members = get_employees_reporting_to(emp_code)
is_manager = len(team_members) > 0

render_sidebar_brand()
with st.sidebar:
    if emp.get("pic_path") and os.path.exists(emp["pic_path"]):
        st.image(emp["pic_path"], width=90)
    else:
        st.markdown(f'<div class="hr-avatar" style="width:70px;height:70px;font-size:1.6rem;">{initials(emp["employee_name"])}</div>', unsafe_allow_html=True)
    st.markdown(f"**{emp['employee_name']}** \n{emp.get('designation') or 'Employee'}")
    badge = "EMPLOYEE PORTAL"
    st.markdown(f'<span class="hr-pill pill-active">{badge}</span>', unsafe_allow_html=True)
    if is_manager:
        st.markdown('<span class="hr-pill pill-muted">TEAM LEAD</span>', unsafe_allow_html=True)

render_notification_bell(emp_code, key_prefix="emp")
logout_button()

st.title(f"Welcome, {emp['employee_name'].split(' ')[0]} 👋")
st.caption("Your self-service portal — profile, leave balances, payslips, and company updates.")

bal_map = get_leave_balance_map(emp_code)
c1, c2, c3, c4 = st.columns(4)
with c1: metric_card("Casual Leave (CL)", f"{bal_map.get('CL', 0):g} day(s)" if is_permanent else "N/A")
with c2: metric_card("Sick Leave (SL)", f"{bal_map.get('SL', 0):g} day(s)" if is_permanent else "N/A")
with c3: metric_card("Privilege Leave (PL)", f"{bal_map.get('PL', 0):g} day(s)" if is_permanent else "N/A")
with c4: metric_card("Monthly CTC", f"₹ {emp.get('ctc', 0):,.0f}")

if not is_permanent:
    st.info("ℹ️ You are currently on **Probation**. Leave entitlement and applications unlock once "
             "HR marks your employment type as **Permanent**.")

st.write("")

tab_names = ["🧾 My Profile", "💰 Salary Structure", "🗓️ Leave", "🧾 Payslips", "📁 My Documents", "📢 Announcements", "⚙️ Settings"]
if is_manager:
    tab_names.insert(3, "✅ Team Approvals")

tabs = st.tabs(tab_names)
tab_map = dict(zip(tab_names, tabs))

# ===========================================================================
# PROFILE
# ===========================================================================
with tab_map["🧾 My Profile"]:
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

# ===========================================================================
# SALARY STRUCTURE
# ===========================================================================
with tab_map["💰 Salary Structure"]:
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

# ===========================================================================
# LEAVE
# ===========================================================================
with tab_map["🗓️ Leave"]:
    st.subheader("Apply for Leave")
    if not is_permanent:
        st.warning("🚫 Leave applications are only available to **Permanent** employees. "
                    "Please contact HR if you believe this is incorrect.")
    else:
        st.markdown('<div class="hr-card">', unsafe_allow_html=True)
        bb1, bb2, bb3 = st.columns(3)
        bb1.metric("CL Available", f"{bal_map.get('CL', 0):g}")
        bb2.metric("SL Available", f"{bal_map.get('SL', 0):g}")
        bb3.metric("PL Available", f"{bal_map.get('PL', 0):g}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="hr-card">', unsafe_allow_html=True)
        with st.form("leave_form"):
            lc1, lc2, lc3 = st.columns(3)
            with lc1:
                leave_type_label = st.selectbox("Leave Type", [f"{k} — {v}" for k, v in LEAVE_TYPE_LABELS.items()])
                leave_type = leave_type_label.split(" — ")[0]
            with lc2: from_d = st.date_input("From Date", value=date.today())
            with lc3: to_d = st.date_input("To Date", value=date.today())
            reason = st.text_area("Reason for Leave")
            if emp.get("reporting_boss_code"):
                st.caption(f"This request will be routed to your reporting boss: **{emp.get('reporting_boss')}**")
            else:
                st.caption("No reporting boss is assigned to you — this request will go directly to HR/Admin.")
            apply = st.form_submit_button("Submit Leave Request", use_container_width=True, type="primary")
            if apply:
                if to_d < from_d:
                    st.error("'To' date cannot precede 'From' date.")
                else:
                    days = (to_d - from_d).days + 1
                    ok, msg = apply_leave(emp_code, leave_type, from_d, to_d, days, reason)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("My Leave History")
    my_reqs = get_leave_requests(emp_code)
    if not my_reqs:
        st.info("No leave requests submitted.")
    else:
        for r in my_reqs:
            ltype_label = LEAVE_TYPE_LABELS.get(r["leave_type"], r["leave_type"])
            st.markdown(
                f"""<div class="hr-card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                <div>
                    <b>{ltype_label}</b> · {r['from_date']} to {r['to_date']} ({r['days']:g} day(s))<br>
                    <span style="font-size:0.8rem;opacity:0.7;">Applied on {r['applied_on']}</span>
                </div>
                <div>{status_pill(r['status'])}</div>
                </div>""",
                unsafe_allow_html=True,
            )

# ===========================================================================
# TEAM APPROVALS (only shown to managers)
# ===========================================================================
if is_manager:
    with tab_map["✅ Team Approvals"]:
        st.subheader("Leave Requests From Your Team")
        st.caption("You are the reporting boss for the employee(s) below.")
        team_codes = {m["employee_code"]: m["employee_name"] for m in team_members}
        st.markdown(", ".join(f"**{n}** ({c})" for c, n in team_codes.items()))
        st.markdown("---")

        team_reqs = get_leave_requests(boss_employee_code=emp_code)
        if not team_reqs:
            st.info("No leave requests from your team yet.")
        else:
            filt = st.selectbox("Filter", ["Pending", "All"], key="team_filter")
            shown = [r for r in team_reqs if filt == "All" or r["status"] == "Pending"]
            if not shown:
                st.success("No pending requests — you're all caught up! 🎉")
            for r in shown:
                ename = team_codes.get(r["employee_code"], r["employee_code"])
                ltype_label = LEAVE_TYPE_LABELS.get(r["leave_type"], r["leave_type"])
                st.markdown('<div class="hr-card">', unsafe_allow_html=True)
                cA, cB = st.columns([3, 1])
                with cA:
                    st.markdown(f"**{ename}** ({r['employee_code']}) · {ltype_label} · **{r['from_date']}** to **{r['to_date']}** ({r['days']:g} day(s))")
                    if r.get("reason"):
                        st.caption(f"Reason: {r['reason']}")
                    st.caption(f"Applied on: {r['applied_on']}")
                with cB:
                    st.markdown(status_pill(r["status"]), unsafe_allow_html=True)
                    if r["status"] == "Pending":
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button("✅", key=f"team_ap_{r['id']}", help="Approve"):
                                decide_leave(r["id"], "Approved", decided_by=emp["employee_name"])
                                st.rerun()
                        with b2:
                            if st.button("❌", key=f"team_rj_{r['id']}", help="Reject"):
                                decide_leave(r["id"], "Rejected", decided_by=emp["employee_name"])
                                st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

# ===========================================================================
# PAYSLIPS
# ===========================================================================
with tab_map["🧾 Payslips"]:
    st.subheader("Download Your Payslip")
    available = get_payroll_months_for_employee(emp_code)
    if not available:
        st.info("No payslips are available yet. Your payslip becomes downloadable once HR/Admin "
                 "runs payroll for a given month.")
    else:
        month_labels = [f"{MONTH_NAMES[m-1]} {y}" for m, y in available]
        pick = st.selectbox("Select Month", month_labels)
        idx = month_labels.index(pick)
        month, year = available[idx]
        record = get_payroll_record(emp_code, month, year)
        if record:
            colp1, colp2, colp3 = st.columns(3)
            colp1.metric("Gross Pay", f"₹{record['gross']:,.0f}")
            colp2.metric("Net Pay", f"₹{record['net_pay']:,.0f}")
            colp3.metric("CTC (that month)", f"₹{record['ctc']:,.0f}")
            pdf_bytes = generate_payslip_pdf(emp, record)
            st.download_button(
                f"⬇️ Download Payslip — {pick}",
                data=pdf_bytes,
                file_name=f"Payslip_{emp_code}_{pick.replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )

# ===========================================================================
# DOCUMENTS
# ===========================================================================
with tab_map["📁 My Documents"]:
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

# ===========================================================================
# ANNOUNCEMENTS
# ===========================================================================
with tab_map["📢 Announcements"]:
    st.subheader("Company Announcements")
    anns = get_announcements(10)
    if not anns:
        st.info("No active announcements.")
    for a in anns:
        st.markdown(
            f"""<div class="hr-card"><b>{a['title']}</b>
            <p style="margin:4px 0;">{a['message'] or ''}</p>
            <span style="font-size:0.75rem;opacity:0.7;">{a['created_at']}</span></div>""",
            unsafe_allow_html=True,
        )

# ===========================================================================
# SETTINGS
# ===========================================================================
with tab_map["⚙️ Settings"]:
    st.subheader("Account Settings")
    with st.form("pw_form"):
        new_pw = st.text_input("New Password", type="password")
        confirm_pw = st.text_input("Confirm New Password", type="password")
        change = st.form_submit_button("Update Password", use_container_width=True, type="primary")
        if change:
            if not new_pw or len(new_pw) < 6:
                st.error("Password must be at least 6 characters.")
            elif new_pw != confirm_pw:
                st.error("Passwords do not match.")
            else:
                change_password(st.session_state["username"], new_pw)
                st.success("Password updated successfully.")