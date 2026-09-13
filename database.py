"""
database.py
Handles SQLite database setup, connections, and CRUD operations
for TEC TANIVA HRMS.
"""

import sqlite3
import hashlib
import os
import secrets
import hmac
from datetime import datetime, date

# ---------------------------------------------------------------------------
# SINGLE SHARED DATABASE
# ---------------------------------------------------------------------------
LOCAL_DB_DIR = os.path.join(os.path.dirname(__file__), "database")
os.makedirs(LOCAL_DB_DIR, exist_ok=True)
LOCAL_DB_PATH = os.path.join(LOCAL_DB_DIR, "hr_system.db")
SHARED_DB_DIR = os.path.join(os.path.expanduser("~"), ".tec_taniva_hrms")
os.makedirs(SHARED_DB_DIR, exist_ok=True)
SHARED_DB_PATH = os.path.join(SHARED_DB_DIR, "hr_system.db")
DB_PATH = os.environ.get("HRMS_DB_PATH", LOCAL_DB_PATH)

if not os.path.exists(DB_PATH) and DB_PATH == SHARED_DB_PATH and os.path.exists(LOCAL_DB_PATH):
    try:
        import shutil
        shutil.copy2(LOCAL_DB_PATH, DB_PATH)
    except OSError:
        pass

# ---------------------------------------------------------------------------
# STATUTORY CONSTANTS (India - PF & ESI, FY 2026)
# ---------------------------------------------------------------------------
PF_WAGE_CEILING = 15000.0
EPF_EMPLOYEE_RATE = 0.12
EMPLOYER_PF_TOTAL_RATE = 0.12
EPS_EMPLOYER_RATE = 0.0833
EPS_MAX_MONTHLY = 1250.0
EDLI_EMPLOYER_RATE = 0.005
EDLI_MAX_MONTHLY = 75.0
PF_ADMIN_CHARGE_RATE = 0.005

ESI_WAGE_CEILING_STANDARD = 21000.0
ESI_WAGE_CEILING_PWD = 25000.0
ESI_EMPLOYER_RATE = 0.0325
ESI_EMPLOYEE_RATE = 0.0075

PF_BASIS_OPTIONS = ["capped", "actual"]

LEAVE_TYPE_LABELS = {
    "CL": "Casual Leave",
    "SL": "Sick Leave",
    "PL": "Privilege / Earned Leave",
}
LEAVE_TYPES = list(LEAVE_TYPE_LABELS.keys())

MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]

# ---------------------------------------------------------------------------
# LOSS OF PAY (LOP) / EXTRA DAY CONSTANTS  [NEW]
# ---------------------------------------------------------------------------
# Per-day salary rate = Gross (Basic + DA + HRA + Phone + Others) / STANDARD_WORKING_DAYS.
# This is used both to deduct Loss of Pay days (no leave balance left / probation period
# absence) and to add extra payment for days worked beyond the standard month.
STANDARD_WORKING_DAYS = 26
LOP_EXTRA_TYPES = ["LOP", "EXTRA"]
LOP_EXTRA_TYPE_LABELS = {
    "LOP": "Loss of Pay",
    "EXTRA": "Extra Day Worked",
}


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def _clean_password(password: str) -> str:
    return (password or "").strip()


def hash_password(password: str) -> str:
    raw = _clean_password(password).encode("utf-8")
    salt = secrets.token_bytes(16)
    iterations = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", raw, salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    password = _clean_password(password)
    stored_hash = stored_hash or ""

    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
            iterations = int(iterations)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(actual, expected), False
        except (ValueError, TypeError):
            return False, False

    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, stored_hash), True


def _ensure_column(cur, table, column, coltype_and_default):
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype_and_default}")


def _bootstrap_employees_from_excel(conn):
    if not os.path.exists(os.path.join(os.path.dirname(__file__), "data.xlsx")):
        return 0
    try:
        import pandas as pd
        xls = pd.ExcelFile(os.path.join(os.path.dirname(__file__), "data.xlsx"))
        sheet = xls.sheet_names[0]
        df = pd.read_excel(os.path.join(os.path.dirname(__file__), "data.xlsx"), sheet_name=sheet)
    except Exception:
        return 0
    if "employee_code" not in df.columns or "employee_name" not in df.columns:
        return 0
    imported = 0
    for _, r in df.iterrows():
        code = str(r.get("employee_code", "")).strip()
        name = str(r.get("employee_name", "")).strip()
        if not code or not name or code.lower() == "nan":
            continue
        exists = conn.execute("SELECT id FROM employees WHERE lower(trim(employee_code))=lower(?) LIMIT 1", (code,)).fetchone()
        if not exists:
            cols = []
            vals = []
            for c in df.columns:
                if c == "employee_code":
                    val = code
                elif c == "employee_name":
                    val = name
                else:
                    val = r.get(c)
                    if pd.isna(val):
                        val = None
                    elif hasattr(val, "date"):
                        val = str(val.date())
                    else:
                        val = str(val) if not isinstance(val, (int, float)) else val
                if c in {"employee_code", "employee_name", "dob", "highest_qualification", "date_of_joining", "designation", "reporting_boss", "mobile_number", "uan_number", "esic_number", "employee_type", "emergency_contact_number", "email", "place", "basic_pay", "hra", "phonebill_pay", "others", "pf", "esic_if_applicable", "food_reimbursement", "ctc"}:
                    cols.append(c); vals.append(val)
            try:
                placeholders = ", ".join(["?"] * len(cols))
                conn.execute(f"INSERT INTO employees ({', '.join(cols)}) VALUES ({placeholders})", vals)
                imported += 1
            except Exception:
                continue
    conn.commit()
    employees = conn.execute("SELECT employee_code, employee_name FROM employees").fetchall()
    for emp in employees:
        code = str(emp["employee_code"]).strip().lower()
        user = conn.execute("SELECT id FROM users WHERE lower(trim(employee_code))=lower(?) AND role='employee' LIMIT 1", (code,)).fetchone()
        if not user:
            taken = conn.execute("SELECT id FROM users WHERE username=? LIMIT 1", (code,)).fetchone()
            if not taken:
                conn.execute("INSERT INTO users (username,password_hash,role,employee_code,full_name) VALUES (?,?,?,?,?)", (code, hash_password("Welcome@123"), "employee", emp["employee_code"], emp["employee_name"]))
    conn.commit()
    return imported


def init_db():
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
            boss_employee_code TEXT,
            decided_by TEXT,
            decided_at TEXT,
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leave_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT NOT NULL,
            leave_type TEXT NOT NULL,
            balance REAL DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_code, leave_type)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_code TEXT NOT NULL,
            title TEXT,
            message TEXT,
            related_type TEXT,
            related_id INTEGER,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS payroll_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            basic_pay REAL DEFAULT 0,
            da REAL DEFAULT 0,
            hra REAL DEFAULT 0,
            phonebill_pay REAL DEFAULT 0,
            others REAL DEFAULT 0,
            gross REAL DEFAULT 0,
            employee_pf REAL DEFAULT 0,
            employee_esic REAL DEFAULT 0,
            employer_pf_total REAL DEFAULT 0,
            employer_esic REAL DEFAULT 0,
            ctc REAL DEFAULT 0,
            net_pay REAL DEFAULT 0,
            generated_by TEXT,
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_code, month, year)
        )
    """)

    # ---- Loss of Pay (LOP) / Extra Day records table  [NEW] ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lop_extra_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT NOT NULL,
            record_type TEXT NOT NULL CHECK(record_type IN ('LOP', 'EXTRA')),
            record_date TEXT NOT NULL,
            day_count REAL NOT NULL DEFAULT 1,
            reason TEXT,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_code) REFERENCES employees(employee_code) ON DELETE CASCADE
        )
    """)

    conn.commit()

    for col, decl in [
        ("da", "REAL DEFAULT 0"),
        ("pf_basis", "TEXT DEFAULT 'capped'"),
        ("pf_wage", "REAL DEFAULT 0"),
        ("pf", "REAL DEFAULT 0"),
        ("employer_pf", "REAL DEFAULT 0"),
        ("employer_eps", "REAL DEFAULT 0"),
        ("employer_edli", "REAL DEFAULT 0"),
        ("employer_admin_charges", "REAL DEFAULT 0"),
        ("employer_pf_total", "REAL DEFAULT 0"),
        ("is_pwd", "INTEGER DEFAULT 0"),
        ("esic_wage_ceiling_used", "REAL DEFAULT 0"),
        ("esic_eligible_by_wage", "INTEGER DEFAULT 0"),
        ("employer_esic", "REAL DEFAULT 0"),
        ("employee_esic", "REAL DEFAULT 0"),
        ("reporting_boss_code", "TEXT"),
    ]:
        _ensure_column(cur, "employees", col, decl)

    for col, decl in [
        ("boss_employee_code", "TEXT"),
        ("decided_by", "TEXT"),
        ("decided_at", "TEXT"),
    ]:
        _ensure_column(cur, "leave_requests", col, decl)
    conn.commit()

    # ---- payroll_records: add LOP / Extra Day columns  [NEW] ----
    for col, decl in [
        ("lop_days", "REAL DEFAULT 0"),
        ("lop_amount", "REAL DEFAULT 0"),
        ("extra_days", "REAL DEFAULT 0"),
        ("extra_amount", "REAL DEFAULT 0"),
        ("per_day_rate", "REAL DEFAULT 0"),
    ]:
        _ensure_column(cur, "payroll_records", col, decl)
    conn.commit()

    cur.execute("SELECT id, username FROM users")
    for row in cur.fetchall():
        normalized = _normalize_username(row["username"])
        if normalized != row["username"]:
            cur.execute("UPDATE users SET username = ? WHERE id = ?", (normalized, row["id"]))
    conn.commit()

    cur.execute("SELECT COUNT(*) as c FROM users WHERE role = 'admin'")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
            (_normalize_username("admin"), hash_password("admin123"), "admin", "HR Administrator"),
        )
        conn.commit()

    _bootstrap_employees_from_excel(conn)
    conn.close()


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------

def authenticate_user(username: str, password: str):
    uname = _normalize_username(username)
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ? LIMIT 1", (uname,)).fetchone()
    if not row:
        conn.close()
        return None

    valid, legacy = verify_password(password, row["password_hash"])
    if not valid:
        conn.close()
        return None

    if legacy:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), row["id"]))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()

    result = dict(row)
    conn.close()
    return result


def create_user(username, password, role, employee_code=None, full_name=None):
    conn = get_connection()
    cur = conn.cursor()
    uname = _normalize_username(username)
    try:
        cur.execute(
            """INSERT INTO users (username, password_hash, role, employee_code, full_name)
               VALUES (?, ?, ?, ?, ?)""",
            (uname, hash_password(password), role, employee_code, full_name),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        print(f"DB Error: {e}")
        return False
    finally:
        conn.close()


def username_exists(username: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM users WHERE username = ?", (_normalize_username(username),)
    ).fetchone()
    conn.close()
    return row is not None


def change_password(username: str, new_password: str):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (hash_password(new_password), _normalize_username(username)),
    )
    conn.commit()
    conn.close()


def get_user_by_employee_code(employee_code: str, role: str = "employee"):
    conn = get_connection()
    code = (employee_code or "").strip()
    row = conn.execute(
        "SELECT * FROM users WHERE lower(trim(employee_code)) = lower(?) AND role = ? ORDER BY id DESC LIMIT 1",
        (code, role),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def reset_employee_password(employee_code: str, new_password: str):
    code = (employee_code or "").strip()
    if not code or not _clean_password(new_password):
        return None

    conn = get_connection()
    emp = conn.execute("SELECT employee_code, employee_name FROM employees WHERE lower(trim(employee_code)) = lower(?) LIMIT 1", (code,)).fetchone()
    if not emp:
        conn.close()
        return None

    user = conn.execute(
        "SELECT * FROM users WHERE lower(trim(employee_code)) = lower(?) AND role = 'employee' ORDER BY id DESC LIMIT 1",
        (code,),
    ).fetchone()

    if user:
        username = _normalize_username(user["username"])
        conn.execute(
            "UPDATE users SET username = ?, password_hash = ?, full_name = ? WHERE id = ?",
            (username, hash_password(new_password), emp["employee_name"], user["id"]),
        )
    else:
        username = _normalize_username(code)
        taken = conn.execute("SELECT id FROM users WHERE username = ? LIMIT 1", (username,)).fetchone()
        if taken:
            conn.close()
            return None
        conn.execute(
            "INSERT INTO users (username, password_hash, role, employee_code, full_name) VALUES (?, ?, 'employee', ?, ?)",
            (username, hash_password(new_password), code, emp["employee_name"]),
        )

    conn.commit()
    conn.close()
    return username


def get_database_info():
    conn = get_connection()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    employee_count_value = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    employee_login_count = conn.execute("SELECT COUNT(*) FROM users WHERE role='employee'").fetchone()[0]
    conn.close()
    return {
        "path": DB_PATH,
        "user_count": user_count,
        "employee_count": employee_count_value,
        "employee_login_count": employee_login_count,
    }


def delete_user_login(username: str):
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE username = ?", (_normalize_username(username),))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# CTC CALCULATION
# ---------------------------------------------------------------------------

def calculate_ctc(basic, da, hra, phonebill, others, esic_if_applicable, pf_basis="capped", is_pwd=False):
    b = max(0.0, float(basic or 0))
    d = max(0.0, float(da or 0))
    h = max(0.0, float(hra or 0))
    p = max(0.0, float(phonebill or 0))
    o = max(0.0, float(others or 0))

    if pf_basis not in PF_BASIS_OPTIONS:
        pf_basis = "capped"

    pf_wage_base = b + d
    gross = pf_wage_base + h + p + o

    pf_wage = min(pf_wage_base, PF_WAGE_CEILING) if pf_basis == "capped" else pf_wage_base

    employee_pf = round(pf_wage * EPF_EMPLOYEE_RATE, 2)

    employer_pf_total_12pct = round(pf_wage * EMPLOYER_PF_TOTAL_RATE, 2)
    eps_wage = min(pf_wage, PF_WAGE_CEILING)
    employer_eps = round(min(eps_wage * EPS_EMPLOYER_RATE, EPS_MAX_MONTHLY), 2)
    employer_epf = round(employer_pf_total_12pct - employer_eps, 2)

    employer_edli = round(min(pf_wage * EDLI_EMPLOYER_RATE, EDLI_MAX_MONTHLY), 2)
    employer_admin_charges = round(pf_wage * PF_ADMIN_CHARGE_RATE, 2)
    employer_pf_total = round(employer_epf + employer_eps + employer_edli + employer_admin_charges, 2)

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


# ---------------------------------------------------------------------------
# EMPLOYEE CRUD
# ---------------------------------------------------------------------------

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
    conn.execute("DELETE FROM leave_balances WHERE employee_code = ?", (employee_code,))
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


def get_employees_reporting_to(boss_code: str):
    if not boss_code:
        return []
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM employees WHERE lower(trim(reporting_boss_code)) = lower(?) ORDER BY employee_name",
        (boss_code.strip(),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_statutory_summary():
    conn = get_connection()
    row = conn.execute("""
        SELECT
            COALESCE(SUM(employer_pf), 0)            AS total_employer_epf,
            COALESCE(SUM(employer_eps), 0)           AS total_employer_eps,
            COALESCE(SUM(employer_edli), 0)          AS total_employer_edli,
            COALESCE(SUM(employer_admin_charges), 0) AS total_admin_charges,
            COALESCE(SUM(employer_pf_total), 0)      AS total_employer_pf,
            COALESCE(SUM(employer_esic), 0)          AS total_employer_esic,
            COALESCE(SUM(employee_esic), 0)          AS total_employee_esic,
            COALESCE(SUM(pf), 0)                     AS total_employee_pf,
            COUNT(*)                                 AS employee_count
        FROM employees WHERE status = 'Active'
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# LEAVE BALANCES (admin/HR managed)
# ---------------------------------------------------------------------------

def upsert_leave_balance(employee_code: str, leave_type: str, balance: float):
    code = (employee_code or "").strip()
    ltype = (leave_type or "").strip().upper()
    if not code or ltype not in LEAVE_TYPES:
        return False
    conn = get_connection()
    conn.execute(
        """INSERT INTO leave_balances (employee_code, leave_type, balance, updated_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(employee_code, leave_type)
           DO UPDATE SET balance = excluded.balance, updated_at = CURRENT_TIMESTAMP""",
        (code, ltype, float(balance)),
    )
    conn.commit()
    conn.close()
    return True


def bulk_upsert_leave_balances(rows):
    """rows: iterable of dicts with employee_code, leave_type, leave_balance."""
    ok, failed = 0, 0
    for r in rows:
        code = str(r.get("employee_code", "")).strip()
        ltype = str(r.get("leave_type", "")).strip().upper()
        try:
            bal = float(r.get("leave_balance", 0))
        except (TypeError, ValueError):
            failed += 1
            continue
        if not code or ltype not in LEAVE_TYPES:
            failed += 1
            continue
        if upsert_leave_balance(code, ltype, bal):
            ok += 1
        else:
            failed += 1
    return ok, failed


def get_leave_balances(employee_code: str):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM leave_balances WHERE employee_code = ? ORDER BY leave_type", (employee_code,)
    ).fetchall()
    conn.close()
    existing = {r["leave_type"]: dict(r) for r in rows}
    out = []
    for lt in LEAVE_TYPES:
        if lt in existing:
            out.append(existing[lt])
        else:
            out.append({"employee_code": employee_code, "leave_type": lt, "balance": 0.0, "updated_at": None})
    return out


def get_leave_balance_map(employee_code: str):
    return {b["leave_type"]: b["balance"] for b in get_leave_balances(employee_code)}


def get_all_leave_balances():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM leave_balances ORDER BY employee_code, leave_type").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def adjust_leave_balance(employee_code: str, leave_type: str, delta: float):
    """Add (or subtract, with a negative delta) to an employee's leave balance."""
    current = get_leave_balance_map(employee_code).get(leave_type, 0.0)
    upsert_leave_balance(employee_code, leave_type, current + delta)


# ---------------------------------------------------------------------------
# LEAVE REQUESTS + APPROVAL WORKFLOW
# ---------------------------------------------------------------------------

def apply_leave(employee_code, leave_type, from_date, to_date, days, reason):
    emp = get_employee(employee_code)
    if not emp:
        return False, "Employee record not found."
    if emp.get("employee_type") != "Permanent":
        return False, "Only Permanent employees are eligible to apply for leave. Probation employees are not entitled to paid leave."

    ltype = (leave_type or "").strip().upper()
    if ltype not in LEAVE_TYPES:
        return False, "Invalid leave type."

    balance = get_leave_balance_map(employee_code).get(ltype, 0.0)
    if float(days) > balance:
        return False, f"Insufficient {LEAVE_TYPE_LABELS[ltype]} balance. Available: {balance:g} day(s), requested: {days:g} day(s)."

    boss_code = (emp.get("reporting_boss_code") or "").strip() or None

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO leave_requests (employee_code, leave_type, from_date, to_date, days, reason, boss_employee_code)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (employee_code, ltype, str(from_date), str(to_date), days, reason, boss_code),
    )
    request_id = cur.lastrowid
    conn.commit()
    conn.close()

    emp_name = emp.get("employee_name", employee_code)
    msg = f"{emp_name} ({employee_code}) applied for {LEAVE_TYPE_LABELS.get(ltype, ltype)} from {from_date} to {to_date} ({days:g} day(s))."
    if boss_code:
        create_notification(boss_code, "New Leave Request", msg, "leave_request", request_id)
    create_notification("ADMIN", "New Leave Request", msg, "leave_request", request_id)

    return True, "Leave request submitted successfully."


def get_leave_requests(employee_code=None, boss_employee_code=None, status=None):
    conn = get_connection()
    query = "SELECT * FROM leave_requests WHERE 1=1"
    params = []
    if employee_code:
        query += " AND employee_code = ?"
        params.append(employee_code)
    if boss_employee_code:
        query += " AND lower(trim(boss_employee_code)) = lower(?)"
        params.append(boss_employee_code.strip())
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY applied_on DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def decide_leave(request_id: int, status: str, decided_by: str = None):
    conn = get_connection()
    row = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        conn.close()
        return False
    req = dict(row)

    conn.execute(
        "UPDATE leave_requests SET status = ?, decided_by = ?, decided_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, decided_by, request_id),
    )
    conn.commit()
    conn.close()

    if status == "Approved":
        adjust_leave_balance(req["employee_code"], req["leave_type"], -float(req["days"] or 0))

    decider_label = decided_by or ("HR/Admin" if not req.get("boss_employee_code") else "your reporting manager")
    ltype_label = LEAVE_TYPE_LABELS.get(req["leave_type"], req["leave_type"])
    msg = (f"Your {ltype_label} request ({req['from_date']} to {req['to_date']}, "
           f"{req['days']:g} day(s)) was {status.lower()} by {decider_label}.")
    create_notification(req["employee_code"], f"Leave {status}", msg, "leave_request", request_id)

    emp_name = get_employee(req["employee_code"])
    emp_name = emp_name.get("employee_name", req["employee_code"]) if emp_name else req["employee_code"]
    admin_msg = (f"{emp_name} ({req['employee_code']})'s {ltype_label} request "
                 f"({req['from_date']} to {req['to_date']}) was {status.upper()} by "
                 f"{decided_by or 'HR/Admin'}.")
    create_notification("ADMIN", f"Leave {status}", admin_msg, "leave_request", request_id)
    return True


def get_leave_balance(employee_code: str):
    """Legacy helper kept for backward compatibility (fixed annual pools)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT leave_type, SUM(days) as used FROM leave_requests WHERE employee_code = ? AND status = 'Approved' GROUP BY leave_type",
        (employee_code,),
    ).fetchall()
    conn.close()

    used_map = {r["leave_type"]: r["used"] or 0 for r in rows}
    return {
        "casual_total": 12,
        "casual_used": used_map.get("CL", used_map.get("Casual", 0)),
        "sick_total": 7,
        "sick_used": used_map.get("SL", used_map.get("Sick", 0)),
        "earned_total": 15,
        "earned_used": used_map.get("PL", used_map.get("Earned", 0)),
    }


# ---------------------------------------------------------------------------
# NOTIFICATIONS
# ---------------------------------------------------------------------------

def create_notification(recipient_code, title, message, related_type=None, related_id=None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO notifications (recipient_code, title, message, related_type, related_id)
           VALUES (?, ?, ?, ?, ?)""",
        ((recipient_code or "").strip(), title, message, related_type, related_id),
    )
    conn.commit()
    conn.close()


def get_notifications(recipient_code, unread_only=False, limit=30):
    conn = get_connection()
    query = "SELECT * FROM notifications WHERE recipient_code = ?"
    params = [(recipient_code or "").strip()]
    if unread_only:
        query += " AND is_read = 0"
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_notification_log(recipient_code="ADMIN", related_type=None, limit=500):
    """Full, un-capped notification history for audit purposes (e.g. the
    Admin 'who applied / who approved / who rejected' activity log)."""
    conn = get_connection()
    query = "SELECT * FROM notifications WHERE recipient_code = ?"
    params = [(recipient_code or "").strip()]
    if related_type:
        query += " AND related_type = ?"
        params.append(related_type)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def unread_notification_count(recipient_code):
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM notifications WHERE recipient_code = ? AND is_read = 0",
        ((recipient_code or "").strip(),),
    ).fetchone()
    conn.close()
    return row["c"] if row else 0


def mark_notification_read(notification_id: int):
    conn = get_connection()
    conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()


def mark_all_notifications_read(recipient_code):
    conn = get_connection()
    conn.execute("UPDATE notifications SET is_read = 1 WHERE recipient_code = ?", ((recipient_code or "").strip(),))
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


# ---------------------------------------------------------------------------
# LOSS OF PAY (LOP) & EXTRA DAY RECORDS  [NEW]
# ---------------------------------------------------------------------------
# Admin uploads (or manually enters) LOP records for employees who took leave
# with no balance left / who are in the probation period, and EXTRA records
# for employees who worked beyond the standard STANDARD_WORKING_DAYS-day
# month. Both feed into generate_payroll() below, which converts the day
# counts into a rupee amount using Gross / STANDARD_WORKING_DAYS as the
# per-day rate, and stores everything on the payroll_records snapshot so it
# shows up on the payslip.

def add_lop_extra_record(employee_code, record_type, record_date, day_count, reason="", created_by=None):
    code = (employee_code or "").strip()
    rtype = (record_type or "").strip().upper()
    if not code or rtype not in LOP_EXTRA_TYPES:
        return False
    try:
        days = float(day_count)
    except (TypeError, ValueError):
        return False
    if days <= 0:
        return False
    try:
        rdate = str(record_date)
        y, m = int(rdate[0:4]), int(rdate[5:7])
    except Exception:
        return False

    conn = get_connection()
    conn.execute(
        """INSERT INTO lop_extra_records
           (employee_code, record_type, record_date, day_count, reason, month, year, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (code, rtype, rdate, days, reason, m, y, created_by),
    )
    conn.commit()
    conn.close()
    return True


def bulk_upsert_lop_extra(rows, record_type, created_by=None):
    """rows: iterable of dicts with employee_code, date, reason, days."""
    ok, failed = 0, 0
    for r in rows:
        code = str(r.get("employee_code", "")).strip()
        rdate = str(r.get("date", "")).strip()
        reason = str(r.get("reason", "") or "")
        try:
            days = float(r.get("days", 0))
        except (TypeError, ValueError):
            failed += 1
            continue
        if not code or not rdate or days <= 0:
            failed += 1
            continue
        if add_lop_extra_record(code, record_type, rdate, days, reason, created_by):
            ok += 1
        else:
            failed += 1
    return ok, failed


def delete_lop_extra_record(record_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM lop_extra_records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


def get_lop_extra_records(employee_code=None, month=None, year=None, record_type=None):
    conn = get_connection()
    query = "SELECT * FROM lop_extra_records WHERE 1=1"
    params = []
    if employee_code:
        query += " AND employee_code = ?"
        params.append(employee_code)
    if month:
        query += " AND month = ?"
        params.append(month)
    if year:
        query += " AND year = ?"
        params.append(year)
    if record_type:
        query += " AND record_type = ?"
        params.append(record_type.upper())
    query += " ORDER BY record_date DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lop_extra_summary(employee_code: str, month: int, year: int):
    """Returns total LOP days and total Extra days for one employee/month/year."""
    conn = get_connection()
    lop_row = conn.execute(
        "SELECT COALESCE(SUM(day_count),0) as total FROM lop_extra_records "
        "WHERE employee_code = ? AND month = ? AND year = ? AND record_type = 'LOP'",
        (employee_code, month, year),
    ).fetchone()
    extra_row = conn.execute(
        "SELECT COALESCE(SUM(day_count),0) as total FROM lop_extra_records "
        "WHERE employee_code = ? AND month = ? AND year = ? AND record_type = 'EXTRA'",
        (employee_code, month, year),
    ).fetchone()
    conn.close()
    return {"lop_days": lop_row["total"] or 0.0, "extra_days": extra_row["total"] or 0.0}


# ---------------------------------------------------------------------------
# PAYROLL / PAYSLIP HISTORY
# ---------------------------------------------------------------------------

def _snapshot_from_employee(emp: dict):
    ctc, bd = calculate_ctc(
        emp.get("basic_pay", 0), emp.get("da", 0), emp.get("hra", 0),
        emp.get("phonebill_pay", 0), emp.get("others", 0),
        emp.get("esic_if_applicable", "No"), emp.get("pf_basis", "capped"),
        bool(emp.get("is_pwd", 0)),
    )
    net_pay = round(bd["gross"] - bd["employee_pf"] - bd["employee_esic"], 2)
    return {
        "basic_pay": emp.get("basic_pay", 0) or 0,
        "da": emp.get("da", 0) or 0,
        "hra": emp.get("hra", 0) or 0,
        "phonebill_pay": emp.get("phonebill_pay", 0) or 0,
        "others": emp.get("others", 0) or 0,
        "gross": bd["gross"],
        "employee_pf": bd["employee_pf"],
        "employee_esic": bd["employee_esic"],
        "employer_pf_total": bd["employer_pf_total"],
        "employer_esic": bd["employer_esic"],
        "ctc": ctc,
        "net_pay": net_pay,
    }


def generate_payroll(employee_code: str, month: int, year: int, generated_by: str = None):
    emp = get_employee(employee_code)
    if not emp:
        return False
    snap = _snapshot_from_employee(emp)

    # ---- Loss of Pay (LOP) / Extra Day adjustment  [NEW] ----
    # Per-day rate is based on Gross (Basic + DA + HRA + Phone + Others), NOT CTC,
    # divided by the standard working-day count. LOP days are deducted at this
    # rate; Extra days worked beyond the standard month are added at this rate.
    lop_extra = get_lop_extra_summary(employee_code, month, year)
    lop_days = lop_extra["lop_days"]
    extra_days = lop_extra["extra_days"]
    per_day_rate = round(snap["gross"] / STANDARD_WORKING_DAYS, 2) if STANDARD_WORKING_DAYS else 0.0
    lop_amount = round(per_day_rate * lop_days, 2)
    extra_amount = round(per_day_rate * extra_days, 2)

    snap["lop_days"] = lop_days
    snap["lop_amount"] = lop_amount
    snap["extra_days"] = extra_days
    snap["extra_amount"] = extra_amount
    snap["per_day_rate"] = per_day_rate
    snap["net_pay"] = round(snap["net_pay"] - lop_amount + extra_amount, 2)
    # ---- end LOP / Extra Day adjustment ----

    conn = get_connection()
    conn.execute(
        """INSERT INTO payroll_records
           (employee_code, month, year, basic_pay, da, hra, phonebill_pay, others, gross,
            employee_pf, employee_esic, employer_pf_total, employer_esic, ctc, net_pay,
            lop_days, lop_amount, extra_days, extra_amount, per_day_rate,
            generated_by, generated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)
           ON CONFLICT(employee_code, month, year) DO UPDATE SET
                basic_pay=excluded.basic_pay, da=excluded.da, hra=excluded.hra,
                phonebill_pay=excluded.phonebill_pay, others=excluded.others, gross=excluded.gross,
                employee_pf=excluded.employee_pf, employee_esic=excluded.employee_esic,
                employer_pf_total=excluded.employer_pf_total, employer_esic=excluded.employer_esic,
                ctc=excluded.ctc, net_pay=excluded.net_pay,
                lop_days=excluded.lop_days, lop_amount=excluded.lop_amount,
                extra_days=excluded.extra_days, extra_amount=excluded.extra_amount,
                per_day_rate=excluded.per_day_rate,
                generated_by=excluded.generated_by, generated_at=CURRENT_TIMESTAMP""",
        (employee_code, month, year, snap["basic_pay"], snap["da"], snap["hra"], snap["phonebill_pay"],
         snap["others"], snap["gross"], snap["employee_pf"], snap["employee_esic"],
         snap["employer_pf_total"], snap["employer_esic"], snap["ctc"], snap["net_pay"],
         snap["lop_days"], snap["lop_amount"], snap["extra_days"], snap["extra_amount"], snap["per_day_rate"],
         generated_by),
    )
    conn.commit()
    conn.close()
    return True


def generate_payroll_for_all(month: int, year: int, generated_by: str = None, active_only=True):
    emps = get_all_employees()
    count = 0
    for e in emps:
        if active_only and e.get("status") != "Active":
            continue
        if generate_payroll(e["employee_code"], month, year, generated_by):
            count += 1
    return count


def get_payroll_record(employee_code: str, month: int, year: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM payroll_records WHERE employee_code = ? AND month = ? AND year = ?",
        (employee_code, month, year),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_payroll_months_for_employee(employee_code: str):
    conn = get_connection()
    rows = conn.execute(
        "SELECT month, year FROM payroll_records WHERE employee_code = ? ORDER BY year DESC, month DESC",
        (employee_code,),
    ).fetchall()
    conn.close()
    return [(r["month"], r["year"]) for r in rows]


def get_all_payroll_records(month=None, year=None, employee_code=None):
    conn = get_connection()
    query = "SELECT * FROM payroll_records WHERE 1=1"
    params = []
    if month:
        query += " AND month = ?"
        params.append(month)
    if year:
        query += " AND year = ?"
        params.append(year)
    if employee_code:
        query += " AND employee_code = ?"
        params.append(employee_code)
    query += " ORDER BY year DESC, month DESC, employee_code"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]