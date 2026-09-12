"""Optional one-time import of employees from data.xlsx.
Run only when you intentionally want to import the supplied spreadsheet into SQLite.
Set INITIAL_EMPLOYEE_PASSWORD before running to create portal accounts.
"""
import os
import pandas as pd
from database import init_db, add_employee, get_employee, get_user_by_employee_code, create_user, calculate_ctc

BASE = os.path.dirname(os.path.abspath(__file__))
XLSX = os.path.join(BASE, "data.xlsx")
TEMP_PASSWORD = os.environ.get("INITIAL_EMPLOYEE_PASSWORD", "")

if not TEMP_PASSWORD or len(TEMP_PASSWORD) < 8:
    raise SystemExit("Set INITIAL_EMPLOYEE_PASSWORD to a temporary password of at least 8 characters before importing.")

init_db()
df = pd.read_excel(XLSX).fillna("")
created = 0
accounts = 0
for _, r in df.iterrows():
    code = str(r.get("employee_code", "")).strip()
    name = str(r.get("employee_name", "")).strip()
    if not code or not name:
        continue
    vals = {c: r.get(c, "") for c in [
        "employee_code","employee_name","dob","highest_qualification","date_of_joining","designation",
        "reporting_boss","mobile_number","uan_number","esic_number","employee_type","email",
        "emergency_contact_number","place","basic_pay","hra","phonebill_pay","others","pf",
        "esic_if_applicable","food_reimbursement","ctc"]}
    # Keep dates as ISO strings for SQLite.
    for k in ["dob", "date_of_joining"]:
        if vals[k] != "": vals[k] = pd.to_datetime(vals[k]).date().isoformat()
    ctc, bd = calculate_ctc(vals["basic_pay"], 0, vals["hra"], vals["phonebill_pay"], vals["others"], vals["esic_if_applicable"] or "No")
    vals.update({"da": 0, "pf_basis": "capped", "pf_wage": bd["pf_wage"], "employer_pf": bd["employer_epf"],
                 "employer_eps": bd["employer_eps"], "employer_edli": bd["employer_edli"],
                 "employer_admin_charges": bd["employer_admin_charges"], "employer_pf_total": bd["employer_pf_total"],
                 "is_pwd": 0, "esic_wage_ceiling_used": bd["esi_ceiling"], "esic_eligible_by_wage": int(bd["esic_eligible"]),
                 "employer_esic": bd["employer_esic"], "employee_esic": bd["employee_esic"], "ctc": ctc, "status": "Active"})
    if not get_employee(code):
        if add_employee(vals): created += 1
    if not get_user_by_employee_code(code):
        if create_user(code, TEMP_PASSWORD, "employee", code, name): accounts += 1
print(f"Import complete. Employees created: {created}; portal accounts created: {accounts}.")
