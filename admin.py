"""
admin.py
Admin / HR Dashboard for managing employee master database, CTC structures,
documents, leave balances & approvals, portal logins, payroll and
announcements.
"""

import os
import io
from datetime import date

import streamlit as st
import pandas as pd

from database import (
    init_db, add_employee, update_employee, delete_employee, get_employee,
    get_all_employees, employee_count, next_employee_code, calculate_ctc,
    create_user, username_exists, get_leave_requests, decide_leave,
    get_all_employee_names, add_announcement, get_announcements,
    get_user_by_employee_code, reset_employee_password, get_database_info,
    LEAVE_TYPES, LEAVE_TYPE_LABELS, MONTH_NAMES,
    get_leave_balances, get_all_leave_balances, upsert_leave_balance,
    bulk_upsert_leave_balances, generate_payroll, generate_payroll_for_all,
    get_payroll_record, get_all_payroll_records, get_payroll_months_for_employee,
    get_notification_log, mark_all_notifications_read,
    # ---- Loss of Pay (LOP) / Extra Days  [NEW] ----
    STANDARD_WORKING_DAYS, add_lop_extra_record, bulk_upsert_lop_extra,
    delete_lop_extra_record, get_lop_extra_records, get_lop_extra_summary,
)
from utils import (
    inject_css, render_sidebar_brand, require_login, logout_button,
    metric_card, status_pill, render_notification_bell, initials, get_palette,
    full_logout, render_portal_sidebar,
)
from payslip import generate_payslip_pdf

st.set_page_config(page_title="Admin Dashboard | TEC TANIVA HRMS", page_icon="🛡️", layout="wide")
init_db()
inject_css()
require_login(role="admin")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

render_portal_sidebar(
    recipient_code="ADMIN",
    display_name=st.session_state.get("username", "Admin"),
    subtitle="Admin / HR",
    badges=["ADMIN / HR"],
    key_prefix="admin",
)

col_title, col_logout = st.columns([4, 1])
with col_title:
    #st.title("🛡️ Admin Dashboard")
    #st.caption("Manage employee records, payroll data, documents, leave and portal access.")
    dbi = get_database_info()
    #st.caption(f"Shared database · Employees: {dbi['employee_count']} · Portal users: {dbi['employee_login_count']}")
with col_logout:
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    if st.button("🚪 Sign Out", type="primary", use_container_width=True, key="top_signout"):
        full_logout()

st.markdown("---")

employees = get_all_employees()
total_emp = employee_count()
active_emp = len([e for e in employees if e["status"] == "Active"])
permanent_emp = len([e for e in employees if e.get("employee_type") == "Permanent"])
pending_leaves = len([r for r in get_leave_requests() if r["status"] == "Pending"])
total_ctc = sum(e["ctc"] or 0 for e in employees)

c1, c2, c3, c4, c5 = st.columns(5)
with c1: metric_card("Total Employees", total_emp)
with c2: metric_card("Active", active_emp)
with c3: metric_card("Permanent (Leave-Eligible)", permanent_emp)
with c4: metric_card("Pending Leave Requests", pending_leaves)
with c5: metric_card("Total Monthly CTC", f"₹ {total_ctc:,.0f}")

st.write("")

tab_add, tab_directory, tab_balances, tab_leaves, tab_payroll, tab_lop, tab_access, tab_announce, tab_notiflog = st.tabs(
    ["➕ Onboard Employee", "📇 Directory", "🗂️ Leave Balances",
     "🗓️ Leave Approvals", "💵 Payroll & Payslips", "💸 Loss of Pay / Extra Days",
     "🔐 Portal Access", "📢 Announcements", "🔔 Notification Log"]
)

# ===========================================================================
# TAB: ONBOARD / EDIT EMPLOYEE
# ===========================================================================
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

    boss_options = {"— None —": None}
    for e in employees:
        if not edit_mode or e["employee_code"] != emp.get("employee_code"):
            boss_options[f"{e['employee_name']} ({e['employee_code']})"] = e["employee_code"]
    current_boss_label = "— None —"
    if emp.get("reporting_boss_code"):
        for label, code in boss_options.items():
            if code == emp.get("reporting_boss_code"):
                current_boss_label = label
                break

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
            boss_label = st.selectbox("Reporting Boss (for leave approvals)", list(boss_options.keys()),
                                       index=list(boss_options.keys()).index(current_boss_label))
            mobile_number = st.text_input("Mobile Number", value=emp.get("mobile_number", ""))
        with col3:
            uan_number = st.text_input("UAN Number", value=emp.get("uan_number", ""))
            esic_number = st.text_input("ESIC Number", value=emp.get("esic_number", ""))
            employee_type = st.selectbox(
                "Employee Type", ["Probation", "Permanent"],
                index=0 if emp.get("employee_type") != "Permanent" else 1,
                help="Only Permanent employees are entitled to apply for leave.",
            )
            place = st.text_input("Place", value=emp.get("place", ""))

        col4, col5 = st.columns(2)
        with col4:
            email = st.text_input("Email", value=emp.get("email", ""))
        with col5:
            emergency_contact_number = st.text_input("Emergency Contact Number", value=emp.get("emergency_contact_number", ""))

        st.markdown("---")
        st.subheader("Salary Structure & Statutory Contributions / Deductions")
        s1, s2, s3, s4, s5 = st.columns(5)
        with s1: basic_pay = st.number_input("Basic Pay (₹)", min_value=0.0, value=float(emp.get("basic_pay", 30000.0) or 30000.0), step=500.0)
        with s2: da = st.number_input("Dearness Allowance / DA (₹)", min_value=0.0, value=float(emp.get("da", 0.0) or 0.0), step=500.0, help="Basic + DA together form the statutory 'PF Wage'.")
        with s3: hra = st.number_input("HRA (₹)", min_value=0.0, value=float(emp.get("hra", 5000.0) or 5000.0), step=500.0)
        with s4: phonebill_pay = st.number_input("Phone Bill (₹)", min_value=0.0, value=float(emp.get("phonebill_pay", 2000.0) or 2000.0), step=100.0)
        with s5: others = st.number_input("Others (₹)", min_value=0.0, value=float(emp.get("others", 20000.0) or 20000.0), step=500.0)

        s6, s7, s8 = st.columns(3)
        with s6:
            pf_basis_label = st.selectbox(
                "PF Contribution Basis",
                ["Statutory Ceiling (₹15,000 cap)", "Actual / Full Basis+DA (voluntary higher PF)"],
                index=0 if emp.get("pf_basis", "capped") == "capped" else 1,
                help="Statutory default caps PF wage at ₹15,000. 'Actual' is a joint employer-employee election to contribute 12% on the full Basic+DA — EPS still stays capped at ₹1,250.",
            )
            pf_basis = "capped" if pf_basis_label.startswith("Statutory") else "actual"
        with s7:
            esic_if_applicable = st.selectbox("ESIC Applicable?", ["No", "Yes"], index=1 if emp.get("esic_if_applicable") == "Yes" else 0)
        with s8:
            food_reimbursement = st.selectbox("Food Reimbursement?", ["No", "Yes"], index=1 if emp.get("food_reimbursement") == "Yes" else 0)

        is_pwd = st.checkbox(
            "Employee is a Person with Disability (raises ESIC wage ceiling to ₹25,000)",
            value=bool(emp.get("is_pwd", 0)),
        )

        live_ctc, bd = calculate_ctc(basic_pay, da, hra, phonebill_pay, others, esic_if_applicable, pf_basis, is_pwd)

        st.markdown("###### Suggested statutory deductions (editable below)")
        pf_col, = st.columns(1)
        with pf_col:
            pf = st.number_input(
                "Employee PF Deduction (₹)",
                min_value=0.0,
                value=float(emp.get("pf")) if emp.get("pf") not in (None, 0) else bd["employee_pf"],
                step=50.0,
                help=f"Statutory suggestion: 12% of PF wage (₹{bd['pf_wage']:,.0f}) = ₹{bd['employee_pf']:,.2f}",
            )

        esic_note = ""
        if esic_if_applicable == "Yes" and not bd["esic_eligible"]:
            esic_note = f" ⚠️ Gross wage ₹{bd['gross']:,.0f} exceeds the ESI wage ceiling (₹{bd['esi_ceiling']:,.0f}) — ESIC will NOT be applied."

        basis_note = "Actual/uncapped Basic+DA (voluntary higher PF)" if bd["pf_basis"] == "actual" else "Capped at ₹15,000 statutory ceiling"

        st.markdown(
            f"""
            <div class="hr-metric" style="margin-top:8px; text-align:left;">
                <div class="label">STATUTORY BREAKDOWN</div>
                <table style="width:100%; color:#e2e8f0; font-size:0.85rem; margin-top:8px; border-collapse:collapse;">
                    <tr><td>Gross (Basic + DA + HRA + Phone + Others)</td><td style="text-align:right;">₹ {bd['gross']:,.2f}</td></tr>
                    <tr><td>PF Wage Base (Basic + DA)</td><td style="text-align:right;">₹ {bd['pf_wage_base']:,.2f}</td></tr>
                    <tr><td>PF Wage Used ({basis_note})</td><td style="text-align:right;">₹ {bd['pf_wage']:,.2f}</td></tr>
                    <tr><td>Employer EPF (12% total − EPS)</td><td style="text-align:right;">₹ {bd['employer_epf']:,.2f}</td></tr>
                    <tr><td>Employer EPS (8.33%, capped ₹1,250)</td><td style="text-align:right;">₹ {bd['employer_eps']:,.2f}</td></tr>
                    <tr><td>Employer EDLI (0.5%, capped ₹75)</td><td style="text-align:right;">₹ {bd['employer_edli']:,.2f}</td></tr>
                    <tr><td>EPFO Admin Charges (0.5%)</td><td style="text-align:right;">₹ {bd['employer_admin_charges']:,.2f}</td></tr>
                    <tr><td><b>Employer PF Total</b></td><td style="text-align:right;"><b>₹ {bd['employer_pf_total']:,.2f}</b></td></tr>
                    <tr><td>ESIC Wage Ceiling Used</td><td style="text-align:right;">₹ {bd['esi_ceiling']:,.0f}</td></tr>
                    <tr><td>Employer ESIC (3.25%){' — eligible' if bd['esic_eligible'] else ' — not applied'}</td><td style="text-align:right;">₹ {bd['employer_esic']:,.2f}</td></tr>
                    <tr><td>Employee ESIC (0.75%){' — eligible' if bd['esic_eligible'] else ' — not applied'}</td><td style="text-align:right;">₹ {bd['employee_esic']:,.2f}</td></tr>
                </table>
                <div class="label" style="margin-top:12px;">CALCULATED CTC = GROSS + EMPLOYER PF TOTAL + EMPLOYER ESIC</div>
                <div class="value" style="font-size: 1.8rem; color: #17b6a7;">₹ {live_ctc:,.2f}</div>
                {f'<div style="color:#fbbf24; font-size:0.8rem; margin-top:6px;">{esic_note}</div>' if esic_note else ''}
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
        submitted = st.form_submit_button(submit_label, use_container_width=True, type="primary")

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

                boss_code = boss_options.get(boss_label)
                boss_name = "" if boss_code is None else boss_label.rsplit(" (", 1)[0]

                record = {
                    "employee_name": employee_name.strip(),
                    "dob": str(dob),
                    "highest_qualification": highest_qualification,
                    "date_of_joining": str(date_of_joining),
                    "designation": designation,
                    "reporting_boss": boss_name,
                    "reporting_boss_code": boss_code,
                    "mobile_number": mobile_number,
                    "uan_number": uan_number,
                    "esic_number": esic_number,
                    "employee_type": employee_type,
                    "email": email,
                    "emergency_contact_number": emergency_contact_number,
                    "place": place,
                    "basic_pay": basic_pay,
                    "da": da,
                    "hra": hra,
                    "phonebill_pay": phonebill_pay,
                    "others": others,
                    "pf_basis": pf_basis,
                    "pf_wage": bd["pf_wage"],
                    "pf": pf,
                    "employer_pf": bd["employer_epf"],
                    "employer_eps": bd["employer_eps"],
                    "employer_edli": bd["employer_edli"],
                    "employer_admin_charges": bd["employer_admin_charges"],
                    "employer_pf_total": bd["employer_pf_total"],
                    "is_pwd": 1 if is_pwd else 0,
                    "esic_if_applicable": esic_if_applicable,
                    "esic_wage_ceiling_used": bd["esi_ceiling"],
                    "esic_eligible_by_wage": 1 if bd["esic_eligible"] else 0,
                    "employer_esic": bd["employer_esic"],
                    "employee_esic": bd["employee_esic"],
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

# ===========================================================================
# TAB: DIRECTORY
# ===========================================================================
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

# ===========================================================================
# TAB: LEAVE BALANCES (admin/HR managed)
# ===========================================================================
with tab_balances:
    st.subheader("Leave Balance Management")
    st.caption("Only Permanent employees are eligible for paid leave. HR/Admin controls exactly how many "
               "Casual (CL), Sick (SL) and Privilege (PL) leave days each employee has.")

    st.markdown('<div class="hr-card">', unsafe_allow_html=True)
    st.markdown("##### 📤 Bulk Upload from Excel / CSV")
    st.caption("Required columns: **employee_code**, **leave_type** (CL / SL / PL), **leave_balance**")
    sample = pd.DataFrame({
        "employee_code": ["TT-EMP-0001", "TT-EMP-0001", "TT-EMP-0001"],
        "leave_type": ["CL", "SL", "PL"],
        "leave_balance": [12, 7, 15],
    })
    st.download_button("⬇️ Download Sample Template", sample.to_csv(index=False).encode("utf-8"),
                        "leave_balance_template.csv", "text/csv")

    upload = st.file_uploader("Upload leave balance sheet", type=["xlsx", "xls", "csv"], key="leave_bal_upload")
    if upload is not None:
        try:
            if upload.name.lower().endswith(".csv"):
                udf = pd.read_csv(upload)
            else:
                udf = pd.read_excel(upload)
            udf.columns = [str(c).strip().lower() for c in udf.columns]
            required = {"employee_code", "leave_type", "leave_balance"}
            if not required.issubset(set(udf.columns)):
                st.error(f"File must contain columns: {', '.join(sorted(required))}")
            else:
                st.dataframe(udf, use_container_width=True, hide_index=True)
                if st.button("✅ Confirm & Apply Leave Balances", type="primary", use_container_width=True):
                    ok, failed = bulk_upsert_leave_balances(udf.to_dict("records"))
                    st.success(f"Applied {ok} row(s). {failed} row(s) skipped (check employee code / leave type).")
                    st.rerun()
        except Exception as e:
            st.error(f"Could not read file: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="hr-card">', unsafe_allow_html=True)
    st.markdown("##### ✍️ Manual Adjustment (single employee)")
    if employees:
        codes = {f"{e['employee_name']} ({e['employee_code']})": e["employee_code"] for e in employees}
        pick_b = st.selectbox("Employee", list(codes.keys()), key="bal_emp_pick")
        b_code = codes[pick_b]
        b_type = get_employee(b_code).get("employee_type")
        if b_type != "Permanent":
            st.warning("This employee is on **Probation** and is not eligible for paid leave until marked Permanent.")
        current = {b["leave_type"]: b["balance"] for b in get_leave_balances(b_code)}
        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            cl_val = st.number_input("CL — Casual Leave", min_value=0.0, value=float(current.get("CL", 0)), step=1.0)
        with bc2:
            sl_val = st.number_input("SL — Sick Leave", min_value=0.0, value=float(current.get("SL", 0)), step=1.0)
        with bc3:
            pl_val = st.number_input("PL — Privilege Leave", min_value=0.0, value=float(current.get("PL", 0)), step=1.0)
        if st.button("💾 Save Balances", use_container_width=True):
            upsert_leave_balance(b_code, "CL", cl_val)
            upsert_leave_balance(b_code, "SL", sl_val)
            upsert_leave_balance(b_code, "PL", pl_val)
            st.success(f"Leave balances updated for {b_code}.")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("##### 📋 All Leave Balances")
    all_bal = get_all_leave_balances()
    if all_bal:
        bal_df = pd.DataFrame(all_bal)[["employee_code", "leave_type", "balance", "updated_at"]]
        st.dataframe(bal_df, use_container_width=True, hide_index=True)
    else:
        st.info("No leave balances set yet. Upload a sheet or set them manually above.")

# ===========================================================================
# TAB: LEAVE APPROVALS
# ===========================================================================
with tab_leaves:
    st.subheader("Employee Leave Requests")
    st.caption("Admin/HR can view and decide on every leave request across the company, "
               "regardless of who the reporting boss is.")
    filter_status = st.selectbox("Filter by status", ["All", "Pending", "Approved", "Rejected"], key="leave_filter")
    reqs = get_leave_requests(status=None if filter_status == "All" else filter_status)
    if not reqs:
        st.info("No leave requests found.")
    else:
        for r in reqs:
            emp_r = get_employee(r["employee_code"]) or {}
            st.markdown('<div class="hr-card">', unsafe_allow_html=True)
            cA, cB = st.columns([3, 1])
            with cA:
                ltype_label = LEAVE_TYPE_LABELS.get(r["leave_type"], r["leave_type"])
                st.markdown(f"**{emp_r.get('employee_name', r['employee_code'])}** ({r['employee_code']}) · {ltype_label} · **{r['from_date']}** to **{r['to_date']}** ({r['days']:g} day(s))")
                if r.get("reason"):
                    st.caption(f"Reason: {r['reason']}")
                boss_label = r.get("boss_employee_code") or "— No boss assigned —"
                st.caption(f"Reporting Boss: {boss_label} · Applied on: {r['applied_on']}")
                if r["status"] != "Pending":
                    st.caption(f"Decided by: {r.get('decided_by') or '—'} on {r.get('decided_at') or '—'}")
            with cB:
                st.markdown(status_pill(r["status"]), unsafe_allow_html=True)
                if r["status"] == "Pending":
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅", key=f"ap_{r['id']}", help="Approve"):
                            decide_leave(r["id"], "Approved", decided_by=st.session_state.get("username"))
                            st.rerun()
                    with b2:
                        if st.button("❌", key=f"rj_{r['id']}", help="Reject"):
                            decide_leave(r["id"], "Rejected", decided_by=st.session_state.get("username"))
                            st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

# ===========================================================================
# TAB: PAYROLL & PAYSLIPS
# ===========================================================================
with tab_payroll:
    st.subheader("Payroll Runs")
    st.caption("Snapshot each employee's current salary structure into a monthly payroll record. "
               "Employees can only download payslips for months you have generated.")

    st.markdown('<div class="hr-card">', unsafe_allow_html=True)
    pr1, pr2, pr3 = st.columns([1, 1, 1])
    with pr1:
        run_month = st.selectbox("Month", MONTH_NAMES, index=date.today().month - 1, key="run_month")
    with pr2:
        run_year = st.number_input("Year", min_value=2020, max_value=2100, value=date.today().year, step=1, key="run_year")
    with pr3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if st.button("⚙️ Generate Payroll for All Active Employees", type="primary", use_container_width=True):
            month_num = MONTH_NAMES.index(run_month) + 1
            count = generate_payroll_for_all(month_num, int(run_year), generated_by=st.session_state.get("username"))
            st.success(f"Payroll generated/refreshed for {count} active employee(s) for {run_month} {int(run_year)}.")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("##### 📄 Download Any Employee's Payslip — Any Month, Any Year")
    st.markdown('<div class="hr-card">', unsafe_allow_html=True)
    if not employees:
        st.info("Onboard employees first.")
    else:
        codes = {f"{e['employee_name']} ({e['employee_code']})": e["employee_code"] for e in employees}
        d1, d2, d3 = st.columns([2, 1, 1])
        with d1:
            pick_emp = st.selectbox("Employee", list(codes.keys()), key="payslip_emp_pick")
        with d2:
            pick_month = st.selectbox("Month", MONTH_NAMES, index=date.today().month - 1, key="payslip_month_pick")
        with d3:
            pick_year = st.number_input("Year", min_value=2020, max_value=2100, value=date.today().year, step=1, key="payslip_year_pick")

        target_code = codes[pick_emp]
        target_month = MONTH_NAMES.index(pick_month) + 1
        record = get_payroll_record(target_code, target_month, int(pick_year))

        if record is None:
            st.warning("No payroll snapshot exists yet for this employee/month/year.")
            if st.button("Generate this snapshot now from current salary structure", use_container_width=True):
                generate_payroll(target_code, target_month, int(pick_year), generated_by=st.session_state.get("username"))
                st.rerun()
        else:
            emp_full = get_employee(target_code)
            pdf_bytes = generate_payslip_pdf(emp_full, record)
            st.download_button(
                f"⬇️ Download Payslip — {pick_month} {int(pick_year)}",
                data=pdf_bytes,
                file_name=f"Payslip_{target_code}_{pick_month}_{int(pick_year)}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("##### 📊 All Generated Payroll Records")
    all_pay = get_all_payroll_records()
    if all_pay:
        pay_df = pd.DataFrame(all_pay)[["employee_code", "month", "year", "gross", "lop_days", "lop_amount", "extra_days", "extra_amount", "net_pay", "ctc", "generated_by", "generated_at"]]
        pay_df["month"] = pay_df["month"].apply(lambda m: MONTH_NAMES[m - 1])
        st.dataframe(pay_df, use_container_width=True, hide_index=True)
    else:
        st.info("No payroll records generated yet.")

# ===========================================================================
# TAB: LOSS OF PAY (LOP) / EXTRA DAYS  [NEW]
# ===========================================================================
with tab_lop:
    st.subheader("Loss of Pay (LOP) & Extra Day Adjustments")
    st.caption(
        f"Per-day salary rate = Gross (Basic + DA + HRA + Phone + Others) ÷ {STANDARD_WORKING_DAYS} standard "
        "working days — **not** CTC. Loss of Pay is recorded when an employee has no leave balance left, or is "
        "on leave during the probation period. Extra Days is recorded when an employee works beyond the "
        f"standard {STANDARD_WORKING_DAYS}-day month. Both are saved to the database immediately, and are "
        "automatically applied the next time you generate/refresh payroll for the affected month — the "
        "amount then shows up on that employee's payslip."
    )

    lop_subtab, extra_subtab, records_subtab = st.tabs(
        ["📉 Loss of Pay", "📈 Extra Days Worked", "📋 All Records"]
    )

    # -------------------- LOSS OF PAY --------------------
    with lop_subtab:
        st.markdown('<div class="hr-card">', unsafe_allow_html=True)
        st.markdown("##### 📤 Bulk Upload Loss of Pay (Excel / CSV)")
        st.caption("Required columns: **employee_code**, **date**, **reason**, **days** "
                   "(use `0.5` for half day, `1` for full day — decimals also work for multi-day spans).")
        lop_sample = pd.DataFrame({
            "employee_code": ["TT-EMP-0001", "TT-EMP-0001"],
            "date": ["2026-09-05", "2026-09-12"],
            "reason": ["No leave balance remaining", "Absence during probation period"],
            "days": [1, 0.5],
        })
        st.download_button(
            "⬇️ Download Sample Template",
            lop_sample.to_csv(index=False).encode("utf-8"),
            "loss_of_pay_template.csv", "text/csv", key="lop_sample_dl",
        )

        lop_upload = st.file_uploader("Upload Loss of Pay sheet", type=["xlsx", "xls", "csv"], key="lop_upload")
        if lop_upload is not None:
            try:
                if lop_upload.name.lower().endswith(".csv"):
                    lop_udf = pd.read_csv(lop_upload)
                else:
                    lop_udf = pd.read_excel(lop_upload)
                lop_udf.columns = [str(c).strip().lower() for c in lop_udf.columns]
                required = {"employee_code", "date", "reason", "days"}
                if not required.issubset(set(lop_udf.columns)):
                    st.error(f"File must contain columns: {', '.join(sorted(required))}")
                else:
                    st.dataframe(lop_udf, use_container_width=True, hide_index=True)
                    if st.button("✅ Confirm & Apply Loss of Pay Records", type="primary",
                                 use_container_width=True, key="lop_confirm"):
                        ok, failed = bulk_upsert_lop_extra(
                            lop_udf.to_dict("records"), "LOP",
                            created_by=st.session_state.get("username"),
                        )
                        st.success(f"Applied {ok} Loss of Pay record(s). {failed} row(s) skipped "
                                   "(check employee code / date / days).")
                        st.rerun()
            except Exception as e:
                st.error(f"Could not read file: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="hr-card">', unsafe_allow_html=True)
        st.markdown("##### ✍️ Manual Entry (single record)")
        if employees:
            codes_lop = {f"{e['employee_name']} ({e['employee_code']})": e["employee_code"] for e in employees}
            with st.form("lop_manual_form"):
                lp1, lp2, lp3 = st.columns(3)
                with lp1:
                    lop_pick = st.selectbox("Employee", list(codes_lop.keys()), key="lop_manual_emp")
                with lp2:
                    lop_date = st.date_input("Date", value=date.today(), key="lop_manual_date")
                with lp3:
                    lop_days_val = st.selectbox(
                        "Days", [1.0, 0.5],
                        format_func=lambda x: "1 (Full Day)" if x == 1.0 else "0.5 (Half Day)",
                        key="lop_manual_days",
                    )
                lop_reason = st.text_input(
                    "Reason", value="No leave balance / probation period absence", key="lop_manual_reason",
                )
                lop_submit = st.form_submit_button("➕ Add Loss of Pay Record", use_container_width=True, type="primary")
                if lop_submit:
                    ok = add_lop_extra_record(
                        codes_lop[lop_pick], "LOP", lop_date, lop_days_val, lop_reason,
                        created_by=st.session_state.get("username"),
                    )
                    if ok:
                        st.success("Loss of Pay record added.")
                        st.rerun()
                    else:
                        st.error("Could not add record. Please check the inputs.")
        else:
            st.info("Onboard employees first.")
        st.markdown("</div>", unsafe_allow_html=True)

    # -------------------- EXTRA DAYS --------------------
    with extra_subtab:
        st.markdown('<div class="hr-card">', unsafe_allow_html=True)
        st.markdown("##### 📤 Bulk Upload Extra Days Worked (Excel / CSV)")
        st.caption("Required columns: **employee_code**, **date**, **reason**, **days** "
                   f"(extra day(s) worked beyond the standard {STANDARD_WORKING_DAYS}-day month).")
        extra_sample = pd.DataFrame({
            "employee_code": ["TT-EMP-0001", "TT-EMP-0001"],
            "date": ["2026-09-06", "2026-09-13"],
            "reason": ["Worked on weekly off", "Worked on holiday"],
            "days": [1, 1],
        })
        st.download_button(
            "⬇️ Download Sample Template",
            extra_sample.to_csv(index=False).encode("utf-8"),
            "extra_days_template.csv", "text/csv", key="extra_sample_dl",
        )

        extra_upload = st.file_uploader("Upload Extra Days sheet", type=["xlsx", "xls", "csv"], key="extra_upload")
        if extra_upload is not None:
            try:
                if extra_upload.name.lower().endswith(".csv"):
                    extra_udf = pd.read_csv(extra_upload)
                else:
                    extra_udf = pd.read_excel(extra_upload)
                extra_udf.columns = [str(c).strip().lower() for c in extra_udf.columns]
                required = {"employee_code", "date", "reason", "days"}
                if not required.issubset(set(extra_udf.columns)):
                    st.error(f"File must contain columns: {', '.join(sorted(required))}")
                else:
                    st.dataframe(extra_udf, use_container_width=True, hide_index=True)
                    if st.button("✅ Confirm & Apply Extra Day Records", type="primary",
                                 use_container_width=True, key="extra_confirm"):
                        ok, failed = bulk_upsert_lop_extra(
                            extra_udf.to_dict("records"), "EXTRA",
                            created_by=st.session_state.get("username"),
                        )
                        st.success(f"Applied {ok} Extra Day record(s). {failed} row(s) skipped "
                                   "(check employee code / date / days).")
                        st.rerun()
            except Exception as e:
                st.error(f"Could not read file: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="hr-card">', unsafe_allow_html=True)
        st.markdown("##### ✍️ Manual Entry (single record)")
        if employees:
            codes_extra = {f"{e['employee_name']} ({e['employee_code']})": e["employee_code"] for e in employees}
            with st.form("extra_manual_form"):
                ep1, ep2, ep3 = st.columns(3)
                with ep1:
                    extra_pick = st.selectbox("Employee", list(codes_extra.keys()), key="extra_manual_emp")
                with ep2:
                    extra_date = st.date_input("Date", value=date.today(), key="extra_manual_date")
                with ep3:
                    extra_days_val = st.number_input("Days", min_value=0.5, value=1.0, step=0.5, key="extra_manual_days")
                extra_reason = st.text_input(
                    "Reason", value="Worked beyond standard working days", key="extra_manual_reason",
                )
                extra_submit = st.form_submit_button("➕ Add Extra Day Record", use_container_width=True, type="primary")
                if extra_submit:
                    ok = add_lop_extra_record(
                        codes_extra[extra_pick], "EXTRA", extra_date, extra_days_val, extra_reason,
                        created_by=st.session_state.get("username"),
                    )
                    if ok:
                        st.success("Extra Day record added.")
                        st.rerun()
                    else:
                        st.error("Could not add record. Please check the inputs.")
        else:
            st.info("Onboard employees first.")
        st.markdown("</div>", unsafe_allow_html=True)

    # -------------------- ALL RECORDS --------------------
    with records_subtab:
        st.markdown("##### 📋 All Loss of Pay / Extra Day Records")
        rec_filter = st.selectbox(
            "Filter by type", ["All", "Loss of Pay (LOP)", "Extra Days (EXTRA)"], key="lop_extra_filter",
        )
        rtype = None
        if rec_filter.startswith("Loss"):
            rtype = "LOP"
        elif rec_filter.startswith("Extra"):
            rtype = "EXTRA"
        all_lop_extra = get_lop_extra_records(record_type=rtype)
        if not all_lop_extra:
            st.info("No records yet. Upload a sheet or add entries manually above.")
        else:
            rec_df = pd.DataFrame(all_lop_extra)[
                ["id", "employee_code", "record_type", "record_date", "day_count", "reason", "created_by", "created_at"]
            ]
            rec_df.columns = ["ID", "Employee Code", "Type", "Date", "Days", "Reason", "Added By", "Added On"]
            st.dataframe(rec_df, use_container_width=True, hide_index=True)

            del_id = st.number_input(
                "Record ID to delete (see ID column above)", min_value=0, step=1, value=0, key="lop_extra_del_id",
            )
            if st.button("🗑️ Delete Record by ID", key="lop_extra_del_btn"):
                if del_id > 0:
                    delete_lop_extra_record(int(del_id))
                    st.success(f"Record {int(del_id)} deleted. Re-run payroll for the affected month to update the payslip.")
                    st.rerun()
                else:
                    st.warning("Enter a valid record ID first.")

            st.download_button(
                "⬇️ Export All Records to CSV",
                rec_df.to_csv(index=False).encode("utf-8"),
                "lop_extra_records.csv", "text/csv", use_container_width=True, key="lop_extra_export",
            )

# ===========================================================================
# TAB: PORTAL ACCESS
# ===========================================================================
with tab_access:
    st.subheader("Employee Portal Login Access")
    if not employees:
        st.info("Add employees first before generating portal login credentials.")
    else:
        names = get_all_employee_names()
        opt = {f"{n['employee_name']} ({n['employee_code']})": n["employee_code"] for n in names}
        pick2 = st.selectbox("Employee", list(opt.keys()), key="access_emp_pick")
        sel_emp_code = opt[pick2]

        if st.session_state.get("last_access_emp_code") != sel_emp_code:
            st.session_state["last_access_emp_code"] = sel_emp_code
            st.session_state.pop("last_generated_creds", None)

        existing_user = get_user_by_employee_code(sel_emp_code)

        st.markdown('<div class="hr-card">', unsafe_allow_html=True)

        if existing_user:
            st.success(f"This employee already has a portal login: **{existing_user['username']}**")
            st.caption(
                "If they can't sign in, reset the password below rather than trying to create a "
                "second account — the login is tied one-to-one with this employee code."
            )
            with st.form("reset_access_form"):
                reset_password = st.text_input(
                    "New Password",
                    value="Welcome@123",
                    help="Shown in plain text on purpose — this is a temporary password you'll read out or copy to the employee, not a secret of yours.",
                )
                do_reset = st.form_submit_button("Reset Password", use_container_width=True)
                if do_reset:
                    pwd = reset_password.strip()
                    if len(pwd) < 4:
                        st.error("Password should be at least 4 characters.")
                    else:
                        uname = reset_employee_password(sel_emp_code, pwd)
                        if uname:
                            st.session_state["last_generated_creds"] = {"username": uname, "password": pwd}
                            st.success(f"Portal login repaired/reset successfully for {sel_emp_code}.")
                            st.rerun()
                        else:
                            st.error("Could not reset the portal login. Verify that this employee exists and that the username is not used by another account.")
        else:
            with st.form("access_form"):
                new_username = st.text_input("Username", value=sel_emp_code)
                new_password = st.text_input(
                    "Temporary Password",
                    value="Welcome@123",
                    help="Shown in plain text on purpose — this is a temporary password you'll read out or copy to the employee, not a secret of yours.",
                )
                create = st.form_submit_button("Generate Login Credentials", use_container_width=True)
                if create:
                    uname = new_username.strip()
                    pwd = new_password.strip()
                    if not uname:
                        st.error("Username is required.")
                    elif not pwd:
                        st.error("Password is required.")
                    elif username_exists(uname):
                        st.error("That username is already taken by another account — pick a different one.")
                    else:
                        success = create_user(uname, pwd, "employee", sel_emp_code)
                        if success:
                            st.session_state["last_generated_creds"] = {"username": uname, "password": pwd}
                            st.success(f"Login created for {pick2}.")
                            st.rerun()
                        else:
                            st.error("Failed to create user login account.")

        st.markdown("</div>", unsafe_allow_html=True)

        creds = st.session_state.get("last_generated_creds")
        if creds:
            st.markdown("##### Credentials to share with the employee")
            st.code(f"Username: {creds['username']}\nPassword: {creds['password']}", language=None)
            st.caption(
                "Copy these exactly — logins are matched without case-sensitivity and with "
                "whitespace trimmed, but it's still best to hand over the exact text above. "
                "This box clears when you pick a different employee."
            )

# ===========================================================================
# TAB: ANNOUNCEMENTS
# ===========================================================================
with tab_announce:
    st.subheader("Publish Company Announcements")
    with st.form("announce_form"):
        title = st.text_input("Notice Title")
        message = st.text_area("Notice Body")
        post = st.form_submit_button("Publish Announcement", use_container_width=True, type="primary")
        if post and title.strip():
            add_announcement(title.strip(), message.strip())
            st.success("Announcement published successfully to employee portal feeds.")
            st.rerun()

    st.markdown("##### Recent Announcements")
    for a in get_announcements(10):
        st.markdown(
            f"""<div class="hr-card"><b>{a['title']}</b>
            <p style="margin:4px 0;">{a['message'] or ''}</p>
            <span style="font-size:0.75rem;opacity:0.7;">{a['created_at']}</span></div>""",
            unsafe_allow_html=True,
        )

# ===========================================================================
# TAB: FULL NOTIFICATION / AUDIT LOG
# ===========================================================================
with tab_notiflog:
    st.subheader("Company-Wide Leave Activity Log")
    st.caption("Every leave event — who applied, who approved it, who rejected it, and when — "
               "not just the last few shown in the sidebar bell.")

    if st.button("Mark everything as read", key="notiflog_mark_all"):
        mark_all_notifications_read("ADMIN")
        st.rerun()

    log = get_notification_log("ADMIN", limit=1000)
    if not log:
        st.info("No leave activity recorded yet.")
    else:
        log_df = pd.DataFrame(log)[["created_at", "title", "message", "is_read"]]
        log_df.columns = ["When", "Event", "Details", "Read"]
        log_df["Read"] = log_df["Read"].map({1: "✅", 0: "🔴 Unread"})
        search_log = st.text_input("🔍 Search the log (employee name/code, event type, etc.)", key="notiflog_search")
        if search_log:
            mask = log_df.apply(lambda r: search_log.lower() in " ".join(str(v).lower() for v in r), axis=1)
            log_df = log_df[mask]
        st.dataframe(log_df, use_container_width=True, hide_index=True, height=520)
        st.download_button(
            "⬇️ Export Full Activity Log to CSV",
            log_df.to_csv(index=False).encode("utf-8"),
            "leave_activity_log.csv", "text/csv", use_container_width=True,
        )