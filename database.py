"""
database.py
Handles SQLite database setup, connections, and CRUD operations
for TEC TANIVA HRMS.

Statutory logic implemented (India, FY 2026 rates as commonly published by EPFO/ESIC):

PROVIDENT FUND (EPF/EPS/EDLI)
    - PF is calculated on "PF Wage" = Basic (+DA, not modelled separately here),
      capped at the statutory wage ceiling of Rs. 15,000/month unless the
      establishment has opted to contribute on full/actual basic.
    - Employee contribution : 12% of PF Wage -> goes fully to the EPF account.
    - Employer contribution (total 12%) is split as:
          3.67%  -> Employees' Provident Fund (EPF)
          8.33%  -> Employees' Pension Scheme (EPS), capped at Rs. 1,250/month
                    (i.e. 8.33% of the Rs. 15,000 ceiling)
      Plus employer-only statutory charges on PF Wage:
          0.50%  -> Employees' Deposit Linked Insurance (EDLI)
          0.50%  -> EPFO Administrative Charges
    - So total employer outgo = EPF + EPS + EDLI + Admin Charges.

EMPLOYEES' STATE INSURANCE (ESI)
    - Applicable only when Gross Wages <= Rs. 21,000/month (statutory wage
      ceiling for ESI coverage) AND the employer has marked the employee as
      ESIC-applicable.
    - Employer contribution : 3.25% of Gross Wages.
    - Employee contribution : 0.75% of Gross Wages (in practice waived for
      average daily wages <= Rs. 176, which is not separately modelled here).

CTC (Cost to Company)
    - CTC = Gross (Basic + HRA + Phone Bill + Others) + Employer PF Total
            + Employer ESIC (if applicable).
    - Employee-side deductions (Employee PF, Employee ESIC) reduce take-home
      pay but do NOT add to CTC - they come out of the Gross component that
      is already counted once.
"""

import sqlite3
import hashlib
import os
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(__file__), "database")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "hr_system.db")

# ---------------------------------------------------------------------------
# STATUTORY CONSTANTS (India - PF & ESI)
# ---------------------------------------------------------------------------
PF_WAGE_CEILING = 15000.0        # Statutory PF wage ceiling (Rs./month)
EPF_EMPLOYEE_RATE = 0.12         # Employee share -> EPF account
EPF_EMPLOYER_RATE = 0.0367       # Employer share -> EPF account
EPS_EMPLOYER_RATE = 0.0833       # Employer share -> Pension Scheme
EPS_MAX_MONTHLY = 1250.0         # 8.33% of 15,000 ceiling, capped
EDLI_EMPLOYER_RATE = 0.005       # Employer share -> EDLI
PF_ADMIN_CHARGE_RATE = 0.005     # Employer share -> EPFO admin charges

ESI_WAGE_CEILING = 21000.0       # Gross wage ceiling for ESI eligibility
ESI_EMPLOYER_RATE = 0.0325       # Employer share of gross wages
ESI_EMPLOYEE_RATE = 0.0075       # Employee share of gross wages


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
            hra REAL DEFAULT 0,
            phonebill_pay REAL DEFAULT 0,
            others REAL DEFAULT 0,

            pf_wage REAL DEFAULT 0,
            pf REAL DEFAULT 0,
            employer_pf REAL DEFAULT 0,
            employer_eps REAL DEFAULT 0,
            employer_edli REAL DEFAULT 0,
            employer_admin_charges REAL DEFAULT 0,
            employer_pf_total REAL DEFAULT 0,

            esic_if_applicable TEXT CHECK(esic_if_applicable IN ('Yes', 'No')) DEFAULT 'No',
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

    # --- Schema migration for installs created before the PF/ESI rework ---
    for col, decl in [
        ("pf_wage", "REAL DEFAULT 0"),
        ("employer_eps", "REAL DEFAULT 0"),
        ("employer_edli", "REAL DEFAULT 0"),
        ("employer_admin_charges", "REAL DEFAULT 0"),
        ("employer_pf_total", "REAL DEFAULT 0"),
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
def calculate_ctc(basic, hra, phonebill, others, esic_if_applicable):
    """
    Computes the full statutory PF and ESI breakdown, and the resulting CTC.

    Returns a tuple: (total_ctc, breakdown_dict)

    breakdown_dict keys:
        gross                -> Basic + HRA + Phone Bill + Others
        pf_wage              -> Basic capped at the Rs. 15,000 PF wage ceiling
        employee_pf          -> Suggested employee PF deduction (12% of pf_wage)
        employer_epf         -> Employer's EPF share (3.67% of pf_wage)
        employer_eps         -> Employer's Pension Scheme share (8.33% of pf_wage, capped Rs.1,250)
        employer_edli        -> Employer's EDLI share (0.5% of pf_wage)
        employer_admin_charges -> EPFO admin charges (0.5% of pf_wage)
        employer_pf_total    -> Sum of all employer PF-related contributions
        esic_eligible        -> True if gross wage <= ESI ceiling AND ESIC marked applicable
        employer_esic        -> Employer ESI share (3.25% of gross, if eligible)
        employee_esic        -> Employee ESI share (0.75% of gross, if eligible)
        total_ctc             -> Final CTC
    """
    b = max(0.0, float(basic or 0))
    h = max(0.0, float(hra or 0))
    p = max(0.0, float(phonebill or 0))
    o = max(0.0, float(others or 0))

    gross = b + h + p + o

    # ---- Provident Fund (statutory wage-ceiling capped) ----
    pf_wage = min(b, PF_WAGE_CEILING)
    employee_pf = round(pf_wage * EPF_EMPLOYEE_RATE, 2)
    employer_epf = round(pf_wage * EPF_EMPLOYER_RATE, 2)
    employer_eps = round(min(pf_wage * EPS_EMPLOYER_RATE, EPS_MAX_MONTHLY), 2)
    employer_edli = round(pf_wage * EDLI_EMPLOYER_RATE, 2)
    employer_admin_charges = round(pf_wage * PF_ADMIN_CHARGE_RATE, 2)
    employer_pf_total = round(employer_epf + employer_eps + employer_edli + employer_admin_charges, 2)

    # ---- ESI (only if gross wage is within the statutory ceiling) ----
    esic_eligible = (esic_if_applicable == "Yes") and (gross <= ESI_WAGE_CEILING)
    employer_esic = round(gross * ESI_EMPLOYER_RATE, 2) if esic_eligible else 0.0
    employee_esic = round(gross * ESI_EMPLOYEE_RATE, 2) if esic_eligible else 0.0

    total_ctc = round(gross + employer_pf_total + employer_esic, 2)

    breakdown = {
        "gross": round(gross, 2),
        "pf_wage": round(pf_wage, 2),
        "employee_pf": employee_pf,
        "employer_epf": employer_epf,
        "employer_eps": employer_eps,
        "employer_edli": employer_edli,
        "employer_admin_charges": employer_admin_charges,
        "employer_pf_total": employer_pf_total,
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