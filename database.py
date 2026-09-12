"""
database.py
Handles SQLite database setup, connections, and CRUD operations
for TEC TANIVA HRMS.

Statutory logic implemented (India, FY 2026 rates as published by EPFO/ESIC):

PROVIDENT FUND (EPF/EPS/EDLI)
    - "PF Wage" = Basic + Dearness Allowance (DA). Retaining allowance is not
      modelled since this app doesn't track it separately.
    - Contribution Basis (chosen per employee):
        "capped"  -> PF Wage is capped at the statutory ceiling of Rs. 15,000/month.
                     This is the default/mandatory basis for employees whose
                     Basic+DA is at or below the ceiling.
        "actual"  -> Employer & employee voluntarily contribute 12% on the full,
                     uncapped Basic+DA (a joint employer/employee election under
                     Para 26(6) of the EPF Scheme). EPS still stays capped.
    - Employee contribution : 12% of PF Wage (per the basis above) -> EPF account.
    - Employer contribution : also 12% of the SAME PF Wage in total, split as:
        - EPS (Pension)  : 8.33% of wage, but ALWAYS capped at the Rs. 15,000
                           ceiling, i.e. max Rs. 1,250/month, regardless of basis.
        - EPF            : the remainder of the employer's 12% after EPS
                           (this is the statutorily correct way to derive it -
                           it only equals a flat 3.67% when PF Wage == ceiling).
      Plus employer-only statutory charges:
        - EDLI                 : 0.5% of PF Wage, capped at Rs. 75/employee/month.
        - EPFO Admin Charges   : 0.5% of PF Wage (on the actual/uncapped wage if
                                  the "actual" basis is chosen - the employer picks
                                  up admin charges on the higher base too). Note:
                                  in real EPFO remittance this is reconciled at the
                                  ESTABLISHMENT level with a Rs. 500/month minimum
                                  (Rs. 75 if there are no contributing members that
                                  month) - this app computes it per-employee as an
                                  estimate for CTC purposes only.

EMPLOYEES' STATE INSURANCE (ESI)
    - Applicable only when Gross Wages <= the ESI wage ceiling AND the employer
      has marked the employee as ESIC-applicable.
    - Wage ceiling is Rs. 21,000/month, or Rs. 25,000/month for employees with
      disabilities.
    - Employer contribution : 3.25% of Gross Wages.
    - Employee contribution : 0.75% of Gross Wages (in practice waived for
      average daily wages <= Rs. 176, not separately modelled here).

CTC (Cost to Company)
    - Gross = Basic + DA + HRA + Phone Bill + Others.
    - CTC = Gross + Employer PF Total (EPF + EPS + EDLI + Admin Charges)
            + Employer ESIC (if applicable).
    - Employee-side deductions (Employee PF, Employee ESIC) reduce take-home
      pay but do NOT add to CTC - they come out of the Gross already counted.
"""

import sqlite3
import hashlib
import os
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(__file__), "database")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "hr_system.db")

# ---------------------------------------------------------------------------
# STATUTORY CONSTANTS (India - PF & ESI, FY 2026)
# ---------------------------------------------------------------------------
PF_WAGE_CEILING = 15000.0        # Statutory PF wage ceiling (Rs./month)
EPF_EMPLOYEE_RATE = 0.12         # Employee share -> EPF account (on PF wage per basis)
EMPLOYER_PF_TOTAL_RATE = 0.12    # Employer's combined EPF+EPS share (on PF wage per basis)
EPS_EMPLOYER_RATE = 0.0833       # Employer's Pension Scheme share, applied to capped wage
EPS_MAX_MONTHLY = 1250.0         # EPS is always capped here (8.33% of 15,000 ceiling)
EDLI_EMPLOYER_RATE = 0.005       # Employer share -> EDLI
EDLI_MAX_MONTHLY = 75.0          # EDLI is capped at Rs.75/employee/month
PF_ADMIN_CHARGE_RATE = 0.005     # Employer share -> EPFO admin charges

ESI_WAGE_CEILING_STANDARD = 21000.0   # Gross wage ceiling for ESI eligibility
ESI_WAGE_CEILING_PWD = 25000.0        # Higher ceiling for employees with disabilities
ESI_EMPLOYER_RATE = 0.0325            # Employer share of gross wages
ESI_EMPLOYEE_RATE = 0.0075            # Employee share of gross wages

PF_BASIS_OPTIONS = ["capped", "actual"]  # "capped" = statutory ceiling, "actual" = voluntary full wage


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _ensure_column(cur, table, column, coltype_and_default):
    """Add a column to an existing table if it doesn't already exist.
    Lets the app evolve its schema without breaking existing installs/data."""
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype_and_default}")


def init_db():
    """Create all required tables, migrate schema, and seed a default admin user if none exists."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'employee')),
            employee_code TEXT,
            full_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT UNIQUE NOT NULL,
            employee_name TEXT NOT NULL,
            dob TEXT,
            highest_qualification TEXT,
            date_of_joining TEXT,
            designation TEXT,
            reporting_boss TEXT,
            mobile_number TEXT,
            uan_number TEXT,
            esic_number TEXT,
            employee_type TEXT CHECK(employee_type IN ('Probation', 'Permanent')),
            emergency_contact_number TEXT,
            email TEXT,
            place TEXT,

            pic_path TEXT,
            id_card_path TEXT,
            certificate_path TEXT,
            cv_path TEXT,
            extra_doc1_path TEXT,
            extra_doc2_path TEXT,
            extra_doc3_path TEXT,
            extra_doc4_path TEXT,

            basic_pay REAL DEFAULT 0,
            da REAL DEFAULT 0,
            hra REAL DEFAULT 0,
            phonebill_pay REAL DEFAULT 0,
            others REAL DEFAULT 0,

            pf_basis TEXT CHECK(pf_basis IN ('capped', 'actual')) DEFAULT 'capped',
            pf_wage REAL DEFAULT 0,
            pf REAL DEFAULT 0,
            employer_pf REAL DEFAULT 0,
            employer_eps REAL DEFAULT 0,
            employer_edli REAL DEFAULT 0,
            employer_admin_charges REAL DEFAULT 0,
            employer_pf_total REAL DEFAULT 0,

            is_pwd INTEGER DEFAULT 0,
            esic_if_applicable TEXT CHECK(esic_if_applicable IN ('Yes', 'No')) DEFAULT 'No',
            esic_wage_ceiling_used REAL DEFAULT 0,
            esic_eligible_by_wage INTEGER DEFAULT 0,
            employer_esic REAL DEFAULT 0,
            employee_esic REAL DEFAULT 0,

            food_reimbursement TEXT CHECK(food_reimbursement IN ('Yes', 'No')) DEFAULT 'No',
            ctc REAL DEFAULT 0,

            leave_balance REAL DEFAULT 12,
            status TEXT DEFAULT 'Active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT NOT NULL,
            leave_type TEXT,
            from_date TEXT,
            to_date TEXT,
            days REAL,
            reason TEXT,
            status TEXT DEFAULT 'Pending',
            applied_on TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_code) REFERENCES employees(employee_code) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # --- Schema migration for installs created before this PF/ESI rework ---
    for col, decl in [
        ("da", "REAL DEFAULT 0"),
        ("pf_basis", "TEXT DEFAULT 'capped'"),
        ("pf_wage", "REAL DEFAULT 0"),
        ("employer_eps", "REAL DEFAULT 0"),
        ("employer_edli", "REAL DEFAULT 0"),
        ("employer_admin_charges", "REAL DEFAULT 0"),
        ("employer_pf_total", "REAL DEFAULT 0"),
        ("is_pwd", "INTEGER DEFAULT 0"),
        ("esic_wage_ceiling_used", "REAL DEFAULT 0"),
        ("esic_eligible_by_wage", "INTEGER DEFAULT 0"),
        ("employee_esic", "REAL DEFAULT 0"),
    ]:
        _ensure_column(cur, "employees", col, decl)
    conn.commit()

    # Seed Default Admin
    cur.execute("SELECT COUNT(*) as c FROM users WHERE role = 'admin'")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
            ("admin", hash_password("admin123"), "admin", "HR Administrator"),
        )
        conn.commit()

    conn.close()


# ---------------------------------------------------------------------------
# AUTHENTICATION & USERS
# ---------------------------------------------------------------------------
def authenticate_user(username: str, password: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE username = ? AND password_hash = ?",
        (username, hash_password(password)),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(username, password, role, employee_code=None, full_name=None):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO users (username, password_hash, role, employee_code, full_name) 
               VALUES (?, ?, ?, ?, ?)""",
            (username, hash_password(password), role, employee_code, full_name),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def username_exists(username: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row is not None


def change_password(username: str, new_password: str):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (hash_password(new_password), username),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# EMPLOYEES & CTC CALCULATION LOGIC
# ---------------------------------------------------------------------------
def calculate_ctc(basic, da, hra, phonebill, others, esic_if_applicable, pf_basis="capped", is_pwd=False):
    """
    Computes the full statutory PF and ESI breakdown, and the resulting CTC.

    Args:
        basic, da, hra, phonebill, others : monthly amounts in Rupees.
        esic_if_applicable : "Yes" / "No" - whether the employer has enrolled
            the employee under ESIC (still subject to the wage-ceiling check).
        pf_basis : "capped" (statutory minimum - PF wage capped at Rs.15,000) or
            "actual" (voluntary joint employer/employee election to contribute
            12% on the full, uncapped Basic+DA). EPS always stays capped.
        is_pwd : True if the employee is a Person with Disability, which raises
            the ESI wage ceiling to Rs.25,000 instead of Rs.21,000.

    Returns a tuple: (total_ctc, breakdown_dict)
    """
    b = max(0.0, float(basic or 0))
    d = max(0.0, float(da or 0))
    h = max(0.0, float(hra or 0))
    p = max(0.0, float(phonebill or 0))
    o = max(0.0, float(others or 0))

    if pf_basis not in PF_BASIS_OPTIONS:
        pf_basis = "capped"

    pf_wage_base = b + d  # Basic + DA is the statutory "PF Wage"
    gross = pf_wage_base + h + p + o

    # ---- Provident Fund ----
    pf_wage = min(pf_wage_base, PF_WAGE_CEILING) if pf_basis == "capped" else pf_wage_base

    employee_pf = round(pf_wage * EPF_EMPLOYEE_RATE, 2)

    employer_pf_total_12pct = round(pf_wage * EMPLOYER_PF_TOTAL_RATE, 2)
    eps_wage = min(pf_wage, PF_WAGE_CEILING)  # EPS is ALWAYS restricted to the ceiling
    employer_eps = round(min(eps_wage * EPS_EMPLOYER_RATE, EPS_MAX_MONTHLY), 2)
    employer_epf = round(employer_pf_total_12pct - employer_eps, 2)

    employer_edli = round(min(pf_wage * EDLI_EMPLOYER_RATE, EDLI_MAX_MONTHLY), 2)
    employer_admin_charges = round(pf_wage * PF_ADMIN_CHARGE_RATE, 2)
    employer_pf_total = round(employer_epf + employer_eps + employer_edli + employer_admin_charges, 2)

    # ---- ESI (wage ceiling depends on disability status) ----
    esi_ceiling = ESI_WAGE_CEILING_PWD if is_pwd else ESI_WAGE_CEILING_STANDARD
    esic_eligible = (esic_if_applicable == "Yes") and (gross <= esi_ceiling)
    employer_esic = round(gross * ESI_EMPLOYER_RATE, 2) if esic_eligible else 0.0
    employee_esic = round(gross * ESI_EMPLOYEE_RATE, 2) if esic_eligible else 0.0

    total_ctc = round(gross + employer_pf_total + employer_esic, 2)

    breakdown = {
        "gross": round(gross, 2),
        "pf_basis": pf_basis,
        "pf_wage_base": round(pf_wage_base, 2),
        "pf_wage": round(pf_wage, 2),
        "employee_pf": employee_pf,
        "employer_epf": employer_epf,
        "employer_eps": employer_eps,
        "employer_edli": employer_edli,
        "employer_admin_charges": employer_admin_charges,
        "employer_pf_total": employer_pf_total,
        "esi_ceiling": esi_ceiling,
        "esic_eligible": esic_eligible,
        "employer_esic": employer_esic,
        "employee_esic": employee_esic,
        "total_ctc": max(0.0, total_ctc),
    }
    return breakdown["total_ctc"], breakdown


def add_employee(data: dict):
    conn = get_connection()
    cur = conn.cursor()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    try:
        cur.execute(f"INSERT INTO employees ({columns}) VALUES ({placeholders})", list(data.values()))
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        print(f"DB Error: {e}")
        return False
    finally:
        conn.close()


def update_employee(employee_code: str, data: dict):
    conn = get_connection()
    cur = conn.cursor()
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
    try:
        cur.execute(f"UPDATE employees SET {set_clause} WHERE employee_code = ?", list(data.values()) + [employee_code])
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False
    finally:
        conn.close()


def delete_employee(employee_code: str):
    conn = get_connection()
    conn.execute("DELETE FROM employees WHERE employee_code = ?", (employee_code,))
    conn.execute("DELETE FROM users WHERE employee_code = ?", (employee_code,))
    conn.commit()
    conn.close()


def get_all_employees():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM employees ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_employee(employee_code: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM employees WHERE employee_code = ?", (employee_code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def employee_count():
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as c FROM employees").fetchone()
    conn.close()
    return row["c"] if row else 0


def next_employee_code():
    conn = get_connection()
    rows = conn.execute("SELECT employee_code FROM employees").fetchall()
    conn.close()
    nums = []
    for r in rows:
        code = r["employee_code"]
        if code and "-" in code:
            try:
                nums.append(int(code.split("-")[-1]))
            except ValueError:
                pass
    next_id = max(nums) + 1 if nums else 1
    return f"TT-EMP-{next_id:04d}"


def get_all_employee_names():
    conn = get_connection()
    rows = conn.execute("SELECT employee_code, employee_name FROM employees ORDER BY employee_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# COMPANY-WIDE STATUTORY SUMMARY (for the Admin Dashboard)
# ---------------------------------------------------------------------------
def get_statutory_summary():
    """Aggregate employer-side PF & ESI outgo across all active employees.

    NOTE: EPFO admin charges are, in reality, reconciled at the establishment
    level with a Rs.500/month minimum (Rs.75 if there are no contributing
    members that month). This summary reports the per-employee estimate
    summed up; treat it as an approximation, not the exact ECR challan amount.
    """
    conn = get_connection()
    row = conn.execute("""
        SELECT
            COALESCE(SUM(employer_pf), 0)              AS total_employer_epf,
            COALESCE(SUM(employer_eps), 0)             AS total_employer_eps,
            COALESCE(SUM(employer_edli), 0)            AS total_employer_edli,
            COALESCE(SUM(employer_admin_charges), 0)   AS total_admin_charges,
            COALESCE(SUM(employer_pf_total), 0)        AS total_employer_pf,
            COALESCE(SUM(employer_esic), 0)            AS total_employer_esic,
            COALESCE(SUM(employee_esic), 0)            AS total_employee_esic,
            COALESCE(SUM(pf), 0)                       AS total_employee_pf,
            COUNT(*)                                   AS employee_count
        FROM employees WHERE status = 'Active'
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# LEAVES & BALANCES
# ---------------------------------------------------------------------------
def get_leave_balance(employee_code: str):
    conn = get_connection()
    rows = conn.execute(
        "SELECT leave_type, SUM(days) as used FROM leave_requests WHERE employee_code = ? AND status = 'Approved' GROUP BY leave_type",
        (employee_code,),
    ).fetchall()
    conn.close()

    used_map = {r["leave_type"]: r["used"] or 0 for r in rows}
    return {
        "casual_total": 12,
        "casual_used": used_map.get("Casual", 0),
        "sick_total": 7,
        "sick_used": used_map.get("Sick", 0),
        "earned_total": 15,
        "earned_used": used_map.get("Earned", 0),
    }


def apply_leave(employee_code, leave_type, from_date, to_date, days, reason):
    conn = get_connection()
    conn.execute(
        "INSERT INTO leave_requests (employee_code, leave_type, from_date, to_date, days, reason) VALUES (?, ?, ?, ?, ?, ?)",
        (employee_code, leave_type, str(from_date), str(to_date), days, reason),
    )
    conn.commit()
    conn.close()


def get_leave_requests(employee_code=None):
    conn = get_connection()
    if employee_code:
        rows = conn.execute("SELECT * FROM leave_requests WHERE employee_code = ? ORDER BY applied_on DESC", (employee_code,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM leave_requests ORDER BY applied_on DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def decide_leave(request_id: int, status: str):
    conn = get_connection()
    conn.execute("UPDATE leave_requests SET status = ? WHERE id = ?", (status, request_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# ANNOUNCEMENTS
# ---------------------------------------------------------------------------
def add_announcement(title, message):
    conn = get_connection()
    conn.execute("INSERT INTO announcements (title, message) VALUES (?, ?)", (title, message))
    conn.commit()
    conn.close()


def get_announcements(limit=10):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM announcements ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]