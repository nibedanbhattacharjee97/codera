"""
admin.py
Admin Dashboard for managing employee master database, CTC structures,
documents, leave clearances, and portal logins.
"""

import os
import streamlit as st
import pandas as pd
from datetime import date

from database import (
    init_db, add_employee, update_employee, delete_employee, get_employee,
    get_all_employees, employee_count, next_employee_code, calculate_ctc,
    create_user, username_exists, get_leave_requests, decide_leave,
    get_all_employee_names, add_announcement, get_announcements,
)
from utils import (
    inject_css, render_sidebar_brand, require_login,
    metric_card, status_pill, PALETTE,
)

st.set_page_config(page_title="Admin Dashboard | TEC TANIVA HRMS", page_icon="🛡️", layout="wide")
init_db()
inject_css()
require_login(role="admin")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def perform_logout():
    try:
        if hasattr(st, "query_params"):
            st.query_params.clear()
        else:
            st.experimental_set_query_params()
    except Exception:
        pass
    st.session_state.clear()
    st.rerun()

render_sidebar_brand()

with st.sidebar:
    st.markdown(f"**Signed in as** \n{st.session_state.get('username')}")
    st.markdown('<span class="hr-pill pill-active">ADMIN</span>', unsafe_allow_html=True)
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    if st.button("🚪 Sign Out (Sidebar)", use_container_width=True):
        perform_logout()

col_title, col_logout = st.columns([4, 1])
with col_title:
    st.title("Admin Dashboard")
    st.caption("Manage employee records, payroll data, documents, leave and portal access.")

with col_logout:
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    if st.button("🚪 Sign Out", type="primary", use_container_width=True):
        perform_logout()

st.markdown("---")

employees = get_all_employees()
total_emp = employee_count()
active_emp = len([e for e in employees if e["status"] == "Active"])
pending_leaves = len([r for r in get_leave_requests() if r["status"] == "Pending"])
total_ctc = sum(e["ctc"] or 0 for e in employees)

c1, c2, c3, c4 = st.columns(4)
with c1: metric_card("Total Employees", total_emp)
with c2: metric_card("Active", active_emp)
with c3: metric_card("Pending Leave Requests", pending_leaves)
with c4: metric_card("Total Monthly CTC", f"₹ {total_ctc:,.0f}")

st.write("")

tab_add, tab_directory, tab_leaves, tab_access, tab_announce = st.tabs(
    ["➕ Onboard Employee", "📇 Employee Directory", "🗓️ Leave Approvals", "🔐 Portal Access", "📢 Announcements"]
)

with tab_add:
    edit_mode = st.session_state.get("edit_employee_code") is not None
    if edit_mode:
        emp = get_employee(st.session_state["edit_employee_code"])
        st.info(f"Editing employee **{emp['employee_name']}** ({emp['employee_code']})")
        if st.button("Cancel edit / Add new instead"):
            st.session_state.pop("edit_employee_code", None)
            st.rerun()
    else:
        emp = {}

    st.markdown('<div class="hr-card">', unsafe_allow_html=True)
    with st.form("employee_form", clear_on_submit=False):
        st.subheader("Employee Data Master")

        code_default = emp.get("employee_code") or next_employee_code()
        col1, col2, col3 = st.columns(3)
        with col1:
            employee_code = st.text_input("Employee Code", value=code_default, disabled=edit_mode)
            employee_name = st.text_input("Employee Name*", value=emp.get("employee_name", ""))
            dob = st.date_input("Date of Birth", value=pd.to_datetime(emp["dob"]).date() if emp.get("dob") else date(1995, 1, 1))
            highest_qualification = st.text_input("Highest Qualification", value=emp.get("highest_qualification", ""))
        with col2:
            designation = st.text_input("Designation", value=emp.get("designation", ""))
            date_of_joining = st.date_input("Date of Joining", value=pd.to_datetime(emp["date_of_joining"]).date() if emp.get("date_of_joining") else date.today())
            reporting_boss = st.text_input("Reporting Boss", value=emp.get("reporting_boss", ""))
            mobile_number = st.text_input("Mobile Number", value=emp.get("mobile_number", ""))
        with col3:
            uan_number = st.text_input("UAN Number", value=emp.get("uan_number", ""))
            esic_number = st.text_input("ESIC Number", value=emp.get("esic_number", ""))
            employee_type = st.selectbox("Employee Type", ["Probation", "Permanent"], index=0 if emp.get("employee_type") != "Permanent" else 1)
            place = st.text_input("Place", value=emp.get("place", ""))

        col4, col5 = st.columns(2)
        with col4:
            email = st.text_input("Email", value=emp.get("email", ""))
        with col5:
            emergency_contact_number = st.text_input("Emergency Contact Number", value=emp.get("emergency_contact_number", ""))

        st.markdown("---")
        st.subheader("Salary Structure & Contributions / Deductions")
        s1, s2, s3, s4 = st.columns(4)
        with s1: basic_pay = st.number_input("Basic Pay (₹)", min_value=0.0, value=float(emp.get("basic_pay", 30000.0) or 30000.0), step=500.0)
        with s2: hra = st.number_input("HRA (₹)", min_value=0.0, value=float(emp.get("hra", 5000.0) or 5000.0), step=500.0)
        with s3: phonebill_pay = st.number_input("Phone Bill (₹)", min_value=0.0, value=float(emp.get("phonebill_pay", 2000.0) or 2000.0), step=100.0)
        with s4: others = st.number_input("Others (₹)", min_value=0.0, value=float(emp.get("others", 20000.0) or 20000.0), step=500.0)

        s5, s6, s7 = st.columns(3)
        with s5: pf = st.number_input("Employee PF (₹)", min_value=0.0, value=float(emp.get("pf", 1800.0) or 1800.0), step=100.0)
        with s6: esic_if_applicable = st.selectbox("ESIC Applicable?", ["No", "Yes"], index=1 if emp.get("esic_if_applicable") == "Yes" else 0)
        with s7: food_reimbursement = st.selectbox("Food Reimbursement?", ["No", "Yes"], index=1 if emp.get("food_reimbursement") == "Yes" else 0)

        # Unpacking the 3 values from calculate_ctc cleanly
        live_ctc, live_employer_pf, live_employer_esic = calculate_ctc(basic_pay, hra, phonebill_pay, others, esic_if_applicable)
        
        st.markdown(
            f"""
            <div class="hr-metric" style="margin-top:8px;">
                <div class="label">CALCULATED CTC = BASIC + HRA + OTHERS + PHONE BILL + EMPLOYER PF (₹{live_employer_pf:,.2f}) {f"+ EMPLOYER ESIC (₹{live_employer_esic:,.2f})" if esic_if_applicable=='Yes' else ''}</div>
                <div class="value" style="font-size: 1.8rem; color: #17b6a7;">₹ {live_ctc:,.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.subheader("Document Uploads")
        d1, d2 = st.columns(2)
        with d1:
            upload_pic = st.file_uploader("Employee Photo", type=["png", "jpg", "jpeg"])
            upload_id_card = st.file_uploader("ID Card Document", type=["png", "jpg", "jpeg", "pdf"])
            upload_certificate = st.file_uploader("Certificate", type=["png", "jpg", "jpeg", "pdf"])
            upload_cv = st.file_uploader("CV / Resume", type=["pdf", "doc", "docx"])
        with d2:
            extra_doc1 = st.file_uploader("Extra Document 1", type=["png", "jpg", "jpeg", "pdf"])
            extra_doc2 = st.file_uploader("Extra Document 2", type=["png", "jpg", "jpeg", "pdf"])
            extra_doc3 = st.file_uploader("Extra Document 3", type=["png", "jpg", "jpeg", "pdf"])
            extra_doc4 = st.file_uploader("Extra Document 4", type=["png", "jpg", "jpeg", "pdf"])

        submit_label = "Update Employee" if edit_mode else "Save Employee Record"
        submitted = st.form_submit_button(submit_label, use_container_width=True)

        if submitted:
            if not employee_name.strip():
                st.error("Employee Name is required.")
            else:
                def save_file(upload, field_name):
                    if upload is None:
                        return emp.get(field_name) if edit_mode else None
                    fname = f"{employee_code}_{field_name}_{upload.name}"
                    fpath = os.path.join(UPLOAD_DIR, fname)
                    with open(fpath, "wb") as f:
                        f.write(upload.getbuffer())
                    return fpath

                record = {
                    "employee_name": employee_name.strip(),
                    "dob": str(dob),
                    "highest_qualification": highest_qualification,
                    "date_of_joining": str(date_of_joining),
                    "designation": designation,
                    "reporting_boss": reporting_boss,
                    "mobile_number": mobile_number,
                    "uan_number": uan_number,
                    "esic_number": esic_number,
                    "employee_type": employee_type,
                    "email": email,
                    "emergency_contact_number": emergency_contact_number,
                    "place": place,
                    "basic_pay": basic_pay,
                    "hra": hra,
                    "phonebill_pay": phonebill_pay,
                    "others": others,
                    "pf": pf,
                    "employer_pf": live_employer_pf,
                    "esic_if_applicable": esic_if_applicable,
                    "employer_esic": live_employer_esic,
                    "food_reimbursement": food_reimbursement,
                    "ctc": live_ctc,
                    "pic_path": save_file(upload_pic, "pic_path"),
                    "id_card_path": save_file(upload_id_card, "id_card_path"),
                    "certificate_path": save_file(upload_certificate, "certificate_path"),
                    "cv_path": save_file(upload_cv, "cv_path"),
                    "extra_doc1_path": save_file(extra_doc1, "extra_doc1_path"),
                    "extra_doc2_path": save_file(extra_doc2, "extra_doc2_path"),
                    "extra_doc3_path": save_file(extra_doc3, "extra_doc3_path"),
                    "extra_doc4_path": save_file(extra_doc4, "extra_doc4_path"),
                }

                if edit_mode:
                    update_employee(employee_code, record)
                    st.success(f"Employee {employee_name} updated successfully.")
                    st.session_state.pop("edit_employee_code", None)
                else:
                    record["employee_code"] = employee_code
                    add_employee(record)
                    st.success(f"Employee {employee_name} onboarded with code {employee_code}.")
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

with tab_directory:
    st.subheader("Employee Master Directory")
    if not employees:
        st.info("No employees onboarded yet. Add an employee using the 'Onboard Employee' tab.")
    else:
        search = st.text_input("🔍 Search employees by name, code, designation, mobile, email, place, etc.")
        df = pd.DataFrame(employees)
        
        view = df.copy()
        if search:
            mask = view.apply(lambda r: search.lower() in " ".join(str(v).lower() for v in r), axis=1)
            view = view[mask]

        st.dataframe(view, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("##### Record Operations")
        codes = {f"{e['employee_name']} ({e['employee_code']})": e["employee_code"] for e in employees}
        pick = st.selectbox("Select Employee", list(codes.keys()))
        sel_code = codes[pick]
        sel_emp = get_employee(sel_code)

        colA, colB = st.columns([1, 1])
        with colA:
            if st.button("✏️ Edit Selected Employee", use_container_width=True):
                st.session_state["edit_employee_code"] = sel_code
                st.rerun()
        with colB:
            if st.button("🗑️ Delete Employee", use_container_width=True, type="secondary"):
                delete_employee(sel_code)
                st.success("Employee record deleted.")
                st.rerun()

        csv_data = view.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Export Filtered Master Directory to Excel / CSV", 
            csv_data, 
            "employee_master_directory.csv", 
            "text/csv",
            use_container_width=True
        )

with tab_leaves:
    st.subheader("Employee Leave Requests")
    reqs = get_leave_requests()
    if not reqs:
        st.info("No leave requests found.")
    else:
        for r in reqs:
            st.markdown('<div class="hr-card">', unsafe_allow_html=True)
            cA, cB = st.columns([3, 1])
            with cA:
                st.markdown(f"**{r['employee_code']}** · {r['leave_type']} Leave · **{r['from_date']}** to **{r['to_date']}** ({r['days']} day(s))")
                if r.get("reason"):
                    st.caption(f"Reason: {r['reason']}")
                st.caption(f"Applied on: {r['applied_on']}")
            with cB:
                st.markdown(status_pill(r["status"]), unsafe_allow_html=True)
                if r["status"] == "Pending":
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅", key=f"ap_{r['id']}", help="Approve"):
                            decide_leave(r["id"], "Approved")
                            st.rerun()
                    with b2:
                        if st.button("❌", key=f"rj_{r['id']}", help="Reject"):
                            decide_leave(r["id"], "Rejected")
                            st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

with tab_access:
    st.subheader("Create Employee Portal Login Account")
    if not employees:
        st.info("Add employees first before generating portal login credentials.")
    else:
        names = get_all_employee_names()
        opt = {f"{n['employee_name']} ({n['employee_code']})": n["employee_code"] for n in names}
        with st.form("access_form"):
            pick2 = st.selectbox("Employee", list(opt.keys()))
            new_username = st.text_input("Username", value=opt[pick2] if pick2 else "")
            new_password = st.text_input("Temporary Password", type="password", value="Welcome@123")
            create = st.form_submit_button("Generate Login Credentials", use_container_width=True)
            if create:
                if username_exists(new_username):
                    st.error("Username already taken.")
                else:
                    success = create_user(new_username, new_password, "employee", opt[pick2])
                    if success:
                        st.success(f"Login profile generated successfully for {pick2}.")
                    else:
                        st.error("Failed to create user login account.")

with tab_announce:
    st.subheader("Publish Company Announcements")
    with st.form("announce_form"):
        title = st.text_input("Notice Title")
        message = st.text_area("Notice Body")
        post = st.form_submit_button("Publish Announcement", use_container_width=True)
        if post and title.strip():
            add_announcement(title.strip(), message.strip())
            st.success("Announcement published successfully to employee portal feeds.")
            st.rerun()