"""Employee self-service portal. Run with: streamlit run employee_count.py"""
from __future__ import annotations
import os
from datetime import date
import streamlit as st
from database import init_db,get_employee,get_leave_balance,apply_leave,get_leave_requests,change_password,get_announcements
from utils import inject_css,render_sidebar_brand,require_login,logout_button,metric_card,status_pill,PALETTE

st.set_page_config(page_title="Employee Portal | TEC TANIVA HRMS",page_icon="👤",layout="wide",initial_sidebar_state="expanded")
init_db(); inject_css(); require_login("employee")
emp_code=st.session_state.get("employee_code")
if not emp_code: st.error("Your account is not linked to an employee record. Please contact HR/Admin."); st.stop()
emp=get_employee(emp_code)
if not emp: st.error("Employee profile not found. Please contact HR/Admin."); st.stop()

render_sidebar_brand()
with st.sidebar:
    if emp.get("pic_path") and os.path.exists(emp["pic_path"]): st.image(emp["pic_path"],width=90)
    st.markdown(f"**{emp['employee_name']}**\n{emp.get('designation') or 'Employee'}",unsafe_allow_html=True)
    st.markdown('<span class="hr-pill pill-active">EMPLOYEE PORTAL</span>',unsafe_allow_html=True)
logout_button()

first=(emp.get("employee_name") or "Employee").split()[0]
st.title(f"Welcome, {first} 👋")
st.caption("Secure self-service access to your profile, salary, leave and company updates.")

bal=get_leave_balance(emp_code)
casual=max(0,bal['casual_total']-bal['casual_used']); sick=max(0,bal['sick_total']-bal['sick_used']); earned=max(0,bal['earned_total']-bal['earned_used'])
c1,c2,c3,c4=st.columns(4)
with c1: metric_card("Casual Leave Left",f"{casual:g} / {bal['casual_total']:g}")
with c2: metric_card("Sick Leave Left",f"{sick:g} / {bal['sick_total']:g}")
with c3: metric_card("Earned Leave Left",f"{earned:g} / {bal['earned_total']:g}")
with c4: metric_card("Monthly CTC",f"₹ {float(emp.get('ctc') or 0):,.0f}")

profile,pay,leave,docs,news,settings=st.tabs(["🧾 My Profile","💰 Salary Structure","🗓️ Leave Application","📁 My Documents","📢 Announcements","⚙️ Settings"])
with profile:
    st.markdown('<div class="hr-card">',unsafe_allow_html=True)
    a,b=st.columns([1,2])
    with a:
        if emp.get("pic_path") and os.path.exists(emp["pic_path"]): st.image(emp["pic_path"],width=180)
        else: st.caption("No profile photo uploaded")
        st.markdown(status_pill(emp.get("status","Active")),unsafe_allow_html=True)
    with b:
        st.subheader(emp['employee_name']); st.caption(f"{emp.get('designation') or 'Employee'} · {emp['employee_code']}")
        x,y=st.columns(2)
        with x:
            st.write(f"**Date of Birth:** {emp.get('dob') or '—'}"); st.write(f"**Date of Joining:** {emp.get('date_of_joining') or '—'}"); st.write(f"**Qualification:** {emp.get('highest_qualification') or '—'}"); st.write(f"**Employee Type:** {emp.get('employee_type') or '—'}")
        with y:
            st.write(f"**Reporting Boss:** {emp.get('reporting_boss') or '—'}"); st.write(f"**Mobile:** {emp.get('mobile_number') or '—'}"); st.write(f"**Email:** {emp.get('email') or '—'}"); st.write(f"**Place:** {emp.get('place') or '—'}")
        st.write(f"**Emergency Contact:** {emp.get('emergency_contact_number') or '—'}")
        st.write(f"**UAN:** {emp.get('uan_number') or '—'}  ·  **ESIC No.:** {emp.get('esic_number') or '—'}")
    st.markdown('</div>',unsafe_allow_html=True)

with pay:
    st.subheader("Salary & Compensation Summary")
    vals=[("Basic Pay",'basic_pay'),("DA",'da'),("HRA",'hra'),("Phone Bill",'phonebill_pay'),("Others",'others')]
    cols=st.columns(5)
    for col,(label,key) in zip(cols,vals): col.metric(label,f"₹{float(emp.get(key) or 0):,.0f}")
    st.divider(); st.markdown("##### Employee Deductions")
    esic=emp.get('esic_if_applicable')=='Yes' and bool(emp.get('esic_eligible_by_wage'))
    d1,d2=st.columns(2); d1.metric("Employee PF",f"₹{float(emp.get('pf') or 0):,.0f}"); d2.metric("Employee ESIC (0.75%)",f"₹{float(emp.get('employee_esic') or 0):,.0f}" if esic else "Not Applicable")
    st.divider(); st.markdown("##### Employer Contributions")
    e1,e2,e3=st.columns(3); e1.metric("Employer PF Total",f"₹{float(emp.get('employer_pf_total') or 0):,.0f}"); e2.metric("Employer ESIC (3.25%)",f"₹{float(emp.get('employer_esic') or 0):,.0f}" if esic else "Not Applicable"); e3.metric("ESIC Status","Eligible" if esic else "Not Applicable")
    basis="Actual / Full Basic+DA" if emp.get('pf_basis')=='actual' else "Statutory Ceiling (₹15,000 cap)"; ceiling=float(emp.get('esic_wage_ceiling_used') or 21000)
    st.caption(f"PF Basis: **{basis}** · ESIC Wage Ceiling: **₹{ceiling:,.0f}**")
    st.markdown(f'<div class="hr-metric"><div class="label">Total Monthly CTC</div><div class="value">₹ {float(emp.get("ctc") or 0):,.2f}</div></div>',unsafe_allow_html=True)

with leave:
    st.subheader("Apply for Leave")
    with st.form("leave_form"):
        a,b,c=st.columns(3); leave_type=a.selectbox("Leave Type",["Casual","Sick","Earned"]); from_d=b.date_input("From Date",date.today()); to_d=c.date_input("To Date",date.today()); reason=st.text_area("Reason",max_chars=500)
        submitted=st.form_submit_button("Submit Leave Request",type="primary",use_container_width=True)
        if submitted:
            if to_d<from_d: st.error("To Date cannot be before From Date.")
            else:
                days=(to_d-from_d).days+1; balance_key={'Casual':('casual_total','casual_used'),'Sick':('sick_total','sick_used'),'Earned':('earned_total','earned_used')}[leave_type]; available=bal[balance_key[0]]-bal[balance_key[1]]
                if days>available: st.error(f"Insufficient {leave_type.lower()} leave balance. Available: {available:g} day(s).")
                elif not reason.strip(): st.error("Please provide a reason for leave.")
                else: apply_leave(emp_code,leave_type,from_d,to_d,days,reason); st.success("Leave request submitted successfully."); st.rerun()
    st.subheader("My Leave History")
    reqs=get_leave_requests(emp_code)
    if not reqs: st.info("No leave requests submitted.")
    for r in reqs:
        st.markdown(f'<div class="hr-card"><b>{r["leave_type"]} Leave</b> · {r["from_date"]} to {r["to_date"]} ({r["days"]:g} day(s))<br><span style="color:{PALETTE["muted"]}">{r.get("reason") or "No reason provided"} · Applied {r["applied_on"]}</span><div style="margin-top:8px">{status_pill(r["status"])}</div></div>',unsafe_allow_html=True)

with docs:
    fields=[("ID Card","id_card_path"),("Certificate","certificate_path"),("CV / Resume","cv_path"),("Extra Document 1","extra_doc1_path"),("Extra Document 2","extra_doc2_path"),("Extra Document 3","extra_doc3_path"),("Extra Document 4","extra_doc4_path")]
    cols=st.columns(3)
    for i,(label,key) in enumerate(fields):
        with cols[i%3]:
            st.markdown('<div class="hr-card">',unsafe_allow_html=True); st.write(f"**{label}**"); path=emp.get(key)
            if path and os.path.isfile(path):
                with open(path,'rb') as f: st.download_button("⬇️ Download",f,file_name=os.path.basename(path),key=f"dl_{key}",use_container_width=True)
            else: st.caption("Not uploaded")
            st.markdown('</div>',unsafe_allow_html=True)

with news:
    anns=get_announcements(10)
    if not anns: st.info("No active announcements.")
    for a in anns: st.markdown(f'<div class="hr-card"><b>{a["title"]}</b><p style="color:{PALETTE["muted"]}">{a.get("message") or ""}</p><small>{a["created_at"]}</small></div>',unsafe_allow_html=True)

with settings:
    st.subheader("Change Password")
    st.info("Use at least 8 characters. Your new password is stored using a salted PBKDF2 hash.")
    with st.form("change_password_form"):
        old=st.text_input("Current Password",type="password"); new=st.text_input("New Password",type="password"); confirm=st.text_input("Confirm New Password",type="password"); ok=st.form_submit_button("Update Password",type="primary")
        if ok:
            from database import authenticate_user
            if not authenticate_user(st.session_state['username'],old): st.error("Current password is incorrect.")
            elif len(new)<8: st.error("New password must contain at least 8 characters.")
            elif new!=confirm: st.error("New passwords do not match.")
            elif change_password(st.session_state['username'],new): st.success("Password updated successfully. Please use the new password next time you sign in.")
            else: st.error("Password could not be updated.")
