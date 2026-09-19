"""
admin.py
Admin / HR Dashboard for managing employee master database, CTC structures,
documents, leave balances & approvals, portal logins, payroll and
announcements.
"""

import os
import io
import zipfile
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
    get_notification_log, mark_all_notifications_read, get_leave_request_counts,
    create_notification, clear_db_cache, preload_admin_cache,
    # ---- Loss of Pay (LOP) / Extra Days  [legacy, still available] ----
    STANDARD_WORKING_DAYS, add_lop_extra_record, bulk_upsert_lop_extra,
    delete_lop_extra_record, get_lop_extra_records, get_lop_extra_summary,
    # ---- Monthly Attendance engine  [NEW] ----
    ATTENDANCE_STATUS_LABELS, ATTENDANCE_STATUS_CODES, bulk_upsert_attendance,
    upsert_attendance_day, get_attendance_records, get_attendance_summary,
    get_attendance_matrix, get_all_attendance_summaries, has_attendance_for_month,
    delete_attendance_month,
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

# Warm up database cache on startup for instant lightning performance
if not st.session_state.get("_admin_cache_warmed"):
    with st.spinner("⚡ Caching database for ultra-fast performance..."):
        preload_admin_cache()

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
    dbi = get_database_info()
with col_logout:
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    c_ref, c_out = st.columns([1, 1])
    with c_ref:
        if st.button("🔄 Sync", help="Refresh database cache", use_container_width=True):
            clear_db_cache()
            preload_admin_cache()
            st.rerun()
    with c_out:
        if st.button("🚪 Sign Out", type="primary", use_container_width=True, key="top_signout"):
            full_logout()

st.markdown("---")

employees = get_all_employees()
total_emp = len(employees)
active_emp = len([e for e in employees if e["status"] == "Active"])
permanent_emp = len([e for e in employees if e.get("employee_type") == "Permanent"])
leave_counts = get_leave_request_counts()
pending_leaves = leave_counts.get("Pending", 0)

# NOTE: the old 5th "Total Monthly CTC" KPI card has been removed per request.
c1, c2, c3, c4 = st.columns(4)
with c1: metric_card("Total Employees", total_emp)
with c2: metric_card("Active", active_emp)
with c3: metric_card("Permanent (Leave-Eligible)", permanent_emp)
with c4: metric_card("Pending Leave Requests", pending_leaves)

st.write("")

tab_add, tab_directory, tab_balances, tab_leaves, tab_payroll, tab_attendance, tab_access, tab_announce, tab_notiflog = st.tabs(
    ["➕ Onboard Employee", "📇 Directory", "🗂️ Leave Balances",
     "🗓️ Leave Approvals", "💵 Payroll & Payslips", "📅 Monthly Attendance",
     "🔐 Portal Access", "📢 Announcements", "🔔 Notification Log"]
)


# ===========================================================================
# SHARED EMPLOYEE FORM RENDERER
# Used both by the "Onboard Employee" tab (add mode) and by the "Edit
# Selected Employee" modal popup in the Directory tab (edit mode), so both
# places always offer exactly the same fields and save through exactly the
# same code path.
# ===========================================================================
def render_employee_form(emp: dict, employees_all: list, form_key: str, submit_label: str, edit_mode: bool):
    """Draws the full employee master form. Returns True if the form was
    submitted and the record was saved (caller should st.rerun() after)."""

    boss_options = {"— None —": None}
    for e in employees_all:
        if not edit_mode or e["employee_code"] != emp.get("employee_code"):
            boss_options[f"{e['employee_name']} ({e['employee_code']})"] = e["employee_code"]
    current_boss_label = "— None —"
    if emp.get("reporting_boss_code"):
        for label, code in boss_options.items():
            if code == emp.get("reporting_boss_code"):
                current_boss_label = label
                break

    with st.form(form_key, clear_on_submit=False):
        st.subheader("Employee Data Master")

        code_default = emp.get("employee_code") or next_employee_code()
        col1, col2, col3 = st.columns(3)
        with col1:
            employee_code = st.text_input("Employee Code", value=code_default, disabled=edit_mode, key=f"{form_key}_code")
            employee_name = st.text_input("Employee Name*", value=emp.get("employee_name", ""), key=f"{form_key}_name")
            dob = st.date_input("Date of Birth", value=pd.to_datetime(emp["dob"]).date() if emp.get("dob") else date(1995, 1, 1), key=f"{form_key}_dob")
            highest_qualification = st.text_input("Highest Qualification", value=emp.get("highest_qualification", ""), key=f"{form_key}_qual")
        with col2:
            designation = st.text_input("Designation", value=emp.get("designation", ""), key=f"{form_key}_desig")
            date_of_joining = st.date_input("Date of Joining", value=pd.to_datetime(emp["date_of_joining"]).date() if emp.get("date_of_joining") else date.today(), key=f"{form_key}_doj")
            boss_label = st.selectbox("Reporting Boss (for leave approvals)", list(boss_options.keys()),
                                       index=list(boss_options.keys()).index(current_boss_label), key=f"{form_key}_boss")
            mobile_number = st.text_input("Mobile Number", value=emp.get("mobile_number", ""), key=f"{form_key}_mobile")
        with col3:
            uan_number = st.text_input("UAN Number", value=emp.get("uan_number", ""), key=f"{form_key}_uan")
            esic_number = st.text_input("ESIC Number", value=emp.get("esic_number", ""), key=f"{form_key}_esicno")
            employee_type = st.selectbox(
                "Employee Type", ["Probation", "Permanent"],
                index=0 if emp.get("employee_type") != "Permanent" else 1,
                help="Only Permanent employees are entitled to apply for leave.",
                key=f"{form_key}_etype",
            )
            place = st.text_input("Place", value=emp.get("place", ""), key=f"{form_key}_place")

        col4, col5, col6 = st.columns(3)
        with col4:
            email = st.text_input("Email", value=emp.get("email", ""), key=f"{form_key}_email")
        with col5:
            emergency_contact_number = st.text_input("Emergency Contact Number", value=emp.get("emergency_contact_number", ""), key=f"{form_key}_emrg")
        with col6:
            blood_group = st.selectbox(
                "Blood Group",
                ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
                index=(["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"].index(emp.get("blood_group"))
                       if emp.get("blood_group") in ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"] else 0),
                key=f"{form_key}_bg",
            )

        st.markdown("###### Bank Details (for salary transfer)")
        col7, col8 = st.columns(2)
        with col7:
            bank_name = st.text_input("Bank Name", value=emp.get("bank_name", ""), key=f"{form_key}_bank")
        with col8:
            ifsc_code = st.text_input("IFSC Code", value=emp.get("ifsc_code", ""), key=f"{form_key}_ifsc")

        st.markdown("---")
        st.subheader("Salary Structure & Statutory Contributions / Deductions")
        s1, s2, s3, s4, s5 = st.columns(5)
        with s1: basic_pay = st.number_input("Basic Pay (₹)", min_value=0.0, value=float(emp.get("basic_pay", 30000.0) or 30000.0), step=500.0, key=f"{form_key}_basic")
        with s2: da = st.number_input("Dearness Allowance / DA (₹)", min_value=0.0, value=float(emp.get("da", 0.0) or 0.0), step=500.0, help="Basic + DA together form the statutory 'PF Wage'.", key=f"{form_key}_da")
        with s3: hra = st.number_input("HRA (₹)", min_value=0.0, value=float(emp.get("hra", 5000.0) or 5000.0), step=500.0, key=f"{form_key}_hra")
        with s4: phonebill_pay = st.number_input("Phone Bill (₹)", min_value=0.0, value=float(emp.get("phonebill_pay", 2000.0) or 2000.0), step=100.0, key=f"{form_key}_phone")
        with s5: others = st.number_input("Others (₹)", min_value=0.0, value=float(emp.get("others", 20000.0) or 20000.0), step=500.0, key=f"{form_key}_others")

        s6, s7, s8 = st.columns(3)
        with s6:
            pf_basis_label = st.selectbox(
                "PF Contribution Basis",
                ["Statutory Ceiling (₹15,000 cap)", "Actual / Full Basis+DA (voluntary higher PF)"],
                index=0 if emp.get("pf_basis", "capped") == "capped" else 1,
                help="Statutory default caps PF wage at ₹15,000. 'Actual' is a joint employer-employee election to contribute 12% on the full Basic+DA — EPS still stays capped at ₹1,250.",
                key=f"{form_key}_pfbasis",
            )
            pf_basis = "capped" if pf_basis_label.startswith("Statutory") else "actual"
        with s7:
            esic_if_applicable = st.selectbox("ESIC Applicable?", ["No", "Yes"], index=1 if emp.get("esic_if_applicable") == "Yes" else 0, key=f"{form_key}_esicapp")
        with s8:
            food_reimbursement = st.selectbox("Food Reimbursement?", ["No", "Yes"], index=1 if emp.get("food_reimbursement") == "Yes" else 0, key=f"{form_key}_food")

        is_pwd = st.checkbox(
            "Employee is a Person with Disability (raises ESIC wage ceiling to ₹25,000)",
            value=bool(emp.get("is_pwd", 0)),
            key=f"{form_key}_pwd",
        )

        live_ctc, bd = calculate_ctc(basic_pay, da, hra, phonebill_pay, others, esic_if_applicable, pf_basis, is_pwd)

        pf = st.number_input(
            "Employee PF Deduction (₹)",
            min_value=0.0,
            value=float(emp.get("pf")) if emp.get("pf") not in (None, 0) else bd["employee_pf"],
            step=50.0,
            help=f"Statutory suggestion: 12% of PF wage (₹{bd['pf_wage']:,.0f}) = ₹{bd['employee_pf']:,.2f}",
            key=f"{form_key}_pf",
        )

        st.caption(f"Calculated CTC (Gross + Employer PF + Employer ESIC): **₹ {live_ctc:,.2f}**"
                   + (f" · ⚠️ ESIC not applied — gross exceeds ₹{bd['esi_ceiling']:,.0f} ceiling"
                      if (esic_if_applicable == "Yes" and not bd["esic_eligible"]) else ""))

        st.markdown("---")
        st.subheader("Document Uploads")
        d1, d2 = st.columns(2)
        with d1:
            upload_pic = st.file_uploader("Employee Photo", type=["png", "jpg", "jpeg"], key=f"{form_key}_pic")
            upload_id_card = st.file_uploader("ID Card Document", type=["png", "jpg", "jpeg", "pdf"], key=f"{form_key}_idc")
            upload_certificate = st.file_uploader("Certificate", type=["png", "jpg", "jpeg", "pdf"], key=f"{form_key}_cert")
            upload_cv = st.file_uploader("CV / Resume", type=["pdf", "doc", "docx"], key=f"{form_key}_cv")
        with d2:
            extra_doc1 = st.file_uploader("Extra Document 1", type=["png", "jpg", "jpeg", "pdf"], key=f"{form_key}_ed1")
            extra_doc2 = st.file_uploader("Extra Document 2", type=["png", "jpg", "jpeg", "pdf"], key=f"{form_key}_ed2")
            extra_doc3 = st.file_uploader("Extra Document 3", type=["png", "jpg", "jpeg", "pdf"], key=f"{form_key}_ed3")
            extra_doc4 = st.file_uploader("Extra Document 4", type=["png", "jpg", "jpeg", "pdf"], key=f"{form_key}_ed4")

        submitted = st.form_submit_button(submit_label, use_container_width=True, type="primary")

        if submitted:
            if not employee_name.strip():
                st.error("Employee Name is required.")
                return False

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
                "blood_group": blood_group,
                "bank_name": bank_name,
                "ifsc_code": ifsc_code,
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
            else:
                record["employee_code"] = employee_code
                add_employee(record)
                st.success(f"Employee {employee_name} onboarded with code {employee_code}.")
            return True
        return False


_dialog_decorator = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)


def _open_edit_modal(sel_code):
    emp_to_edit = get_employee(sel_code)
    all_emps = get_all_employees()

    if _dialog_decorator:
        try:
            decorator = _dialog_decorator(f"Edit Employee — {emp_to_edit['employee_name']}", width="large")
        except TypeError:
            decorator = _dialog_decorator(f"Edit Employee — {emp_to_edit['employee_name']}")

        @decorator
        def _modal():
            saved = render_employee_form(emp_to_edit, all_emps, form_key="edit_modal_form", submit_label="💾 Update Employee", edit_mode=True)
            if saved:
                st.session_state.pop("open_edit_modal_for", None)
                st.rerun()
        _modal()
    else:
        st.warning("Your Streamlit version doesn't support popup dialogs — editing inline below instead.")
        saved = render_employee_form(emp_to_edit, all_emps, form_key="edit_modal_form_fallback", submit_label="💾 Update Employee", edit_mode=True)
        if saved:
            st.session_state.pop("open_edit_modal_for", None)
            st.rerun()


# ===========================================================================
# TAB: ONBOARD EMPLOYEE
# ===========================================================================
with tab_add:
    st.markdown('<div class="hr-card">', unsafe_allow_html=True)
    saved = render_employee_form({}, employees, form_key="employee_form", submit_label="Save Employee Record", edit_mode=False)
    if saved:
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

if st.session_state.get("open_edit_modal_for"):
    _open_edit_modal(st.session_state["open_edit_modal_for"])

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
            if st.button("✏️ Edit Selected Employee", use_container_width=True, key="dir_edit_btn"):
                st.session_state["open_edit_modal_for"] = sel_code
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
                    st.success(f"Applied {ok} row(s). {failed} row(s) skipped (check employee code / leave type). "
                               "Affected employees have been notified in their portal.")
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
            create_notification(b_code, "Leave Balance Updated",
                                 "HR has updated your leave balance. Check the Leave tab for your latest CL/SL/PL balance.",
                                 "leave_balance", None)
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
# TAB: LEAVE APPROVALS (Optimized with in-memory employee lookup)
# ===========================================================================
with tab_leaves:
    st.subheader("Employee Leave Requests")
    st.caption("Requests from employees with a reporting boss are routed to that boss for approval first — "
               "they'll decide it from their own portal's Team Approvals tab. Admin/HR only decides directly "
               "when no reporting boss is assigned, or via HR Override below if the boss is unavailable.")

    all_counts = leave_counts
    lc1, lc2, lc3 = st.columns(3)
    with lc1: metric_card("Pending (Company-wide)", all_counts.get("Pending", 0))
    with lc2: metric_card("Approved (Company-wide)", all_counts.get("Approved", 0))
    with lc3: metric_card("Rejected (Company-wide)", all_counts.get("Rejected", 0))
    st.write("")

    filter_status = st.selectbox("Filter by status", ["All", "Pending", "Approved", "Rejected"], key="leave_filter")
    reqs = get_leave_requests(status=None if filter_status == "All" else filter_status)
    if not reqs:
        st.info("No leave requests found.")
    else:
        emp_map = {e["employee_code"]: e for e in employees}
        for r in reqs:
            emp_r = emp_map.get(r["employee_code"]) or get_employee(r["employee_code"]) or {}
            st.markdown('<div class="hr-card">', unsafe_allow_html=True)
            cA, cB = st.columns([3, 1])
            with cA:
                ltype_label = LEAVE_TYPE_LABELS.get(r["leave_type"], r["leave_type"])
                st.markdown(f"**{emp_r.get('employee_name', r['employee_code'])}** ({r['employee_code']}) · {ltype_label} · **{r['from_date']}** to **{r['to_date']}** ({r['days']:g} day(s))")
                if r.get("reason"):
                    st.caption(f"Reason: {r['reason']}")
                boss_code = r.get("boss_employee_code")
                boss_emp = emp_map.get(boss_code) if boss_code else (get_employee(boss_code) if boss_code else None)
                boss_display = boss_emp["employee_name"] if boss_emp else (boss_code or "— No boss assigned —")
                st.caption(f"Reporting Boss: {boss_display} · Applied on: {r['applied_on']}")
                if r["status"] != "Pending":
                    st.caption(f"Decided by: {r.get('decided_by') or '—'} on {r.get('decided_at') or '—'}")
            with cB:
                st.markdown(status_pill(r["status"]), unsafe_allow_html=True)
                if r["status"] == "Pending":
                    if boss_code:
                        st.caption(f"⏳ Awaiting decision from **{boss_display}**")
                        with st.expander("HR Override"):
                            st.caption("Use only if the reporting boss is unavailable. This bypasses their approval.")
                            ob1, ob2 = st.columns(2)
                            with ob1:
                                if st.button("✅ Approve", key=f"ov_ap_{r['id']}", help="HR Override — Approve"):
                                    decide_leave(r["id"], "Approved", decided_by=st.session_state.get("username"))
                                    st.rerun()
                            with ob2:
                                if st.button("❌ Reject", key=f"ov_rj_{r['id']}", help="HR Override — Reject"):
                                    decide_leave(r["id"], "Rejected", decided_by=st.session_state.get("username"))
                                    st.rerun()
                    else:
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
               "Gross = Basic + DA + HRA + Phone + Others. Loss-of-Pay / Extra-day amounts come from "
               "the Monthly Attendance tab if uploaded for that month. Employees can only download "
               "payslips for months you have generated, and are notified automatically when ready.")


    pr1, pr2, pr3 = st.columns([1, 1, 1])
    with pr1:
        run_month = st.selectbox("Month", MONTH_NAMES, index=date.today().month - 1, key="run_month")
    with pr2:
        run_year = st.number_input("Year", min_value=2020, max_value=2100, value=date.today().year, step=1, key="run_year")
    with pr3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if st.button("⚙️ Generate Payroll for All Active Employees", type="primary", use_container_width=True):
            month_num = MONTH_NAMES.index(run_month) + 1
            count = generate_payroll_for_all(month_num, int(run_year), generated_by=st.session_state.get("username"), notify=True)
            st.success(f"Payroll generated/refreshed for {count} active employee(s) for {run_month} {int(run_year)}. "
                       "Each employee has been notified in their portal.")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("##### 📦 Download All Payslips for a Month (ZIP)")
    zip_month = MONTH_NAMES.index(run_month) + 1
    zip_records = get_all_payroll_records(month=zip_month, year=int(run_year))
    if not zip_records:
        st.info(f"No payroll records exist yet for {run_month} {int(run_year)}. Generate payroll above first.")
    else:
        st.caption(f"{len(zip_records)} payslip(s) available for {run_month} {int(run_year)}.")
        if st.button("📦 Build ZIP of All Payslips", use_container_width=True):
            buf = io.BytesIO()
            emp_lookup = {e["employee_code"]: e for e in employees}
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for rec in zip_records:
                    e = emp_lookup.get(rec["employee_code"]) or get_employee(rec["employee_code"])
                    if not e:
                        continue
                    pdf_bytes = generate_payslip_pdf(e, rec)
                    fname = f"Payslip_{rec['employee_code']}_{run_month}_{int(run_year)}.pdf"
                    zf.writestr(fname, pdf_bytes)
            st.session_state["payslip_zip_bytes"] = buf.getvalue()
            st.session_state["payslip_zip_label"] = f"Payslips_{run_month}_{int(run_year)}.zip"
        if st.session_state.get("payslip_zip_bytes"):
            st.download_button(
                f"⬇️ Download {st.session_state.get('payslip_zip_label')}",
                data=st.session_state["payslip_zip_bytes"],
                file_name=st.session_state.get("payslip_zip_label", "payslips.zip"),
                mime="application/zip",
                use_container_width=True,
                type="primary",
            )
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
                generate_payroll(target_code, target_month, int(pick_year), generated_by=st.session_state.get("username"), notify=True)
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
        pay_df = pd.DataFrame(all_pay)[["employee_code", "month", "year", "gross", "present_days", "lop_days", "lop_amount", "extra_days", "extra_amount", "net_pay", "ctc", "source", "generated_by", "generated_at"]]
        pay_df["month"] = pay_df["month"].apply(lambda m: MONTH_NAMES[m - 1])
        st.dataframe(pay_df, use_container_width=True, hide_index=True)
    else:
        st.info("No payroll records generated yet.")

# ===========================================================================
# TAB: MONTHLY ATTENDANCE (Ultra-Fast Batch Engine)
# ===========================================================================
with tab_attendance:
    st.subheader("Monthly Attendance → Payroll")
    st.caption(
        f"Upload one row per employee with a status for each calendar day, and payroll will automatically "
        f"compute Loss-of-Pay / Extra-day amounts from it using Per-Day Rate = Gross (Basic + DA + HRA + "
        f"Phone + Others) ÷ {STANDARD_WORKING_DAYS} standard working days. "
        "Once attendance is uploaded for a month, it takes priority over any old manual Loss-of-Pay entries "
        "for that same month — just re-run Payroll afterwards to apply it to the payslip."
    )

    att_col1, att_col2 = st.columns(2)
    with att_col1:
        att_month_name = st.selectbox("Month", MONTH_NAMES, index=date.today().month - 1, key="att_month")
    with att_col2:
        att_year = st.number_input("Year", min_value=2020, max_value=2100, value=date.today().year, step=1, key="att_year")
    att_month = MONTH_NAMES.index(att_month_name) + 1

    import calendar as _cal
    days_in_month = _cal.monthrange(int(att_year), att_month)[1]

    up_tab, manual_tab, view_tab = st.tabs(["📤 Bulk Upload", "✍️ Manual Grid Entry", "📋 View / Export"])

    # -------------------- BULK UPLOAD --------------------
    with up_tab:
        st.markdown('<div class="hr-card">', unsafe_allow_html=True)
        st.markdown("##### 📤 Upload Monthly Attendance Sheet (Excel / CSV)")
        st.caption(
            "Required columns: **employee_code**, **employee_name** (optional, for readability), "
            f"then one column per day: **1, 2, 3 … {days_in_month}**. "
            "Cell values: " + ", ".join(f"`{k}` = {v}" for k, v in ATTENDANCE_STATUS_LABELS.items())
        )

        sample_cols = {"employee_code": ["TT-EMP-0001", "TT-EMP-0002"], "employee_name": ["Jane Doe", "John Roe"]}
        for d in range(1, days_in_month + 1):
            col_vals = ["P", "P"]
            if d == 5:
                col_vals = ["A", "P"]
            elif d == 6:
                col_vals = ["HD", "P"]
            elif d in (7, 14, 21, 28):
                col_vals = ["WO", "WO"]
            elif d == 15:
                col_vals = ["EX", "P"]
            sample_cols[str(d)] = col_vals
        sample_att_df = pd.DataFrame(sample_cols)
        st.download_button(
            f"⬇️ Download Sample Template ({att_month_name} {int(att_year)}, {days_in_month} days)",
            sample_att_df.to_csv(index=False).encode("utf-8"),
            f"attendance_template_{att_month_name}_{int(att_year)}.csv", "text/csv", key="att_sample_dl",
        )

        att_upload = st.file_uploader("Upload attendance sheet", type=["xlsx", "xls", "csv"], key="att_upload")
        if att_upload is not None:
            try:
                if att_upload.name.lower().endswith(".csv"):
                    att_udf = pd.read_csv(att_upload, dtype=str)
                else:
                    att_udf = pd.read_excel(att_upload, dtype=str)
                att_udf.columns = [str(c).strip().lower() for c in att_udf.columns]
                if "employee_code" not in att_udf.columns:
                    st.error("File must contain an 'employee_code' column.")
                else:
                    st.dataframe(att_udf, use_container_width=True, hide_index=True)
                    day_cols = [str(d) for d in range(1, days_in_month + 1) if str(d) in att_udf.columns]
                    if not day_cols:
                        st.error(f"No day columns (1–{days_in_month}) found in the uploaded file.")
                    else:
                        st.caption(f"Found day columns: {', '.join(day_cols)}")
                        if st.button("✅ Confirm & Apply Attendance", type="primary", use_container_width=True, key="att_confirm"):
                            processed, applied, failed = bulk_upsert_attendance(
                                att_udf.to_dict("records"), att_month, int(att_year),
                                created_by=st.session_state.get("username"), day_columns=day_cols,
                            )
                            st.success(f"Attendance applied for {processed} employee(s), {applied} day-cell(s) recorded, "
                                       f"{failed} cell(s) skipped (unknown code or invalid employee). "
                                       "Re-run Payroll for this month to push these figures onto payslips.")
                            st.rerun()
            except Exception as e:
                st.error(f"Could not read file: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

    # -------------------- MANUAL GRID ENTRY --------------------
    with manual_tab:
        st.markdown('<div class="hr-card">', unsafe_allow_html=True)
        st.markdown("##### ✍️ Quick Manual Entry (single employee, single day)")
        if employees:
            codes_att = {f"{e['employee_name']} ({e['employee_code']})": e["employee_code"] for e in employees}
            with st.form("att_manual_form"):
                ap1, ap2, ap3 = st.columns(3)
                with ap1:
                    att_pick = st.selectbox("Employee", list(codes_att.keys()), key="att_manual_emp")
                with ap2:
                    att_day = st.number_input("Day of Month", min_value=1, max_value=days_in_month, value=1, step=1, key="att_manual_day")
                with ap3:
                    att_status = st.selectbox(
                        "Status", ATTENDANCE_STATUS_CODES,
                        format_func=lambda c: f"{c} — {ATTENDANCE_STATUS_LABELS[c]}",
                        key="att_manual_status",
                    )
                att_submit = st.form_submit_button("➕ Save Day Status", use_container_width=True, type="primary")
                if att_submit:
                    ok = upsert_attendance_day(codes_att[att_pick], att_month, int(att_year), att_day, att_status,
                                                created_by=st.session_state.get("username"))
                    if ok:
                        st.success(f"Saved: {att_pick} → Day {att_day} = {att_status}.")
                        st.rerun()
                    else:
                        st.error("Could not save. Please check the inputs.")
        else:
            st.info("Onboard employees first.")
        st.markdown("</div>", unsafe_allow_html=True)

    # -------------------- VIEW / EXPORT (Zero N+1 Queries) --------------------
    with view_tab:
        st.markdown(f"##### 📋 Attendance Matrix — {att_month_name} {int(att_year)}")
        matrix = get_attendance_matrix(att_month, int(att_year))
        if not matrix:
            st.info("No attendance uploaded yet for this month. Use the Bulk Upload or Manual Entry tabs above.")
        else:
            mat_df = pd.DataFrame(matrix)
            day_cols_present = [str(d) for d in range(1, days_in_month + 1) if str(d) in mat_df.columns]
            mat_df = mat_df[["employee_code", "employee_name"] + day_cols_present]
            st.dataframe(mat_df, use_container_width=True, hide_index=True, height=420)

            st.download_button(
                f"⬇️ Export {att_month_name} {int(att_year)} Attendance to CSV",
                mat_df.to_csv(index=False).encode("utf-8"),
                f"attendance_{att_month_name}_{int(att_year)}.csv", "text/csv", use_container_width=True,
            )

            st.markdown("---")
            st.markdown("##### Per-Employee Summary (this month)")
            summary_rows = get_all_attendance_summaries(att_month, int(att_year))
            if summary_rows:
                summ_df = pd.DataFrame(summary_rows)[
                    ["employee_code", "employee_name", "present_days", "absent_days", "half_days",
                     "extra_days", "week_off_days", "holiday_days", "on_leave_days", "lop_days"]
                ]
                st.dataframe(summ_df, use_container_width=True, hide_index=True)

            st.markdown("---")
            if st.button(f"🗑️ Delete ALL Attendance for {att_month_name} {int(att_year)}", type="secondary"):
                delete_attendance_month(att_month, int(att_year))
                st.success("Attendance data cleared for this month.")
                st.rerun()

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