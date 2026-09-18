"""
database.py
PostgreSQL backend for TEC TANIVA HRMS.
Handles SSL connections, Neon cold-starts, connection pooling, and CRUD.
"""

import os
import secrets
import hashlib
import hmac
import time
from datetime import datetime
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import streamlit as st

# ---------------------------------------------------------------------------
# POSTGRESQL CONNECTION POOL SETUP
# ---------------------------------------------------------------------------
def _get_database_url() -> str:
    # Priority 1: Streamlit Secrets
    if hasattr(st, "secrets"):
        if "postgres" in st.secrets and "url" in st.secrets["postgres"]:
            return st.secrets["postgres"]["url"]
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    # Priority 2: OS Environment Variable
    return os.environ.get("DATABASE_URL", "")

DB_URL = _get_database_url()

@st.cache_resource
def get_connection_pool():
    if not DB_URL:
        raise ValueError("DATABASE_URL not configured. Please add it to Streamlit Secrets or Environment Variables.")
    
    dsn = DB_URL
    # Ensure Neon doesn't drop cold-starts during serverless wakeups
    if "connect_timeout" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "connect_timeout=15"

    # Retry up to 3 times to allow Neon compute to wake from 'Idle' state
    last_err = None
    for attempt in range(3):
        try:
            return psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=dsn
            )
        except psycopg2.OperationalError as e:
            last_err = e
            time.sleep(2)
    raise last_err

def get_connection():
    cp = get_connection_pool()
    conn = cp.getconn()
    conn.autocommit = False
    return conn

def release_connection(conn):
    try:
        cp = get_connection_pool()
        cp.putconn(conn)
    except Exception:
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

STANDARD_WORKING_DAYS = 26
LOP_EXTRA_TYPES = ["LOP", "EXTRA"]
LOP_EXTRA_TYPE_LABELS = {
    "LOP": "Loss of Pay",
    "EXTRA": "Extra Day Worked",
}

ATTENDANCE_STATUS_LABELS = {
    "P":  "Present",
    "A":  "Absent (Loss of Pay - full day)",
    "HD": "Half Day (Loss of Pay - half day)",
    "WO": "Week Off (paid, no deduction)",
    "H":  "Holiday (paid, no deduction)",
    "PL": "On Approved Leave (paid, no deduction)",
    "EX": "Extra Day Worked (paid on top of gross)",
}
ATTENDANCE_STATUS_CODES = list(ATTENDANCE_STATUS_LABELS.keys())
LOP_FULL_CODES = {"A"}
LOP_HALF_CODES = {"HD"}
EXTRA_CODES = {"EX"}
PRESENT_CODES = {"P", "EX"}

# ---------------------------------------------------------------------------
# HELPERS & AUTH
# ---------------------------------------------------------------------------
def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()

def _normalize_employee_code(code) -> str:
    return (str(code) if code is not None else "").strip().upper()

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

# ---------------------------------------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------------------------------------
def init_db():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'employee')),
                    employee_code TEXT,
                    full_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS employees (
                    id SERIAL PRIMARY KEY,
                    employee_code TEXT UNIQUE NOT NULL,
                    employee_name TEXT NOT NULL,
                    dob TEXT,
                    highest_qualification TEXT,
                    date_of_joining TEXT,
                    designation TEXT,
                    reporting_boss TEXT,
                    reporting_boss_code TEXT,
                    mobile_number TEXT,
                    uan_number TEXT,
                    esic_number TEXT,
                    employee_type TEXT CHECK(employee_type IN ('Probation', 'Permanent')),
                    emergency_contact_number TEXT,
                    email TEXT,
                    place TEXT,
                    bank_name TEXT,
                    ifsc_code TEXT,
                    blood_group TEXT,

                    pic_path TEXT,
                    id_card_path TEXT,
                    certificate_path TEXT,
                    cv_path TEXT,
                    extra_doc1_path TEXT,
                    extra_doc2_path TEXT,
                    extra_doc3_path TEXT,
                    extra_doc4_path TEXT,

                    basic_pay DOUBLE PRECISION DEFAULT 0,
                    da DOUBLE PRECISION DEFAULT 0,
                    hra DOUBLE PRECISION DEFAULT 0,
                    phonebill_pay DOUBLE PRECISION DEFAULT 0,
                    others DOUBLE PRECISION DEFAULT 0,

                    pf_basis TEXT CHECK(pf_basis IN ('capped', 'actual')) DEFAULT 'capped',
                    pf_wage DOUBLE PRECISION DEFAULT 0,
                    pf DOUBLE PRECISION DEFAULT 0,
                    employer_pf DOUBLE PRECISION DEFAULT 0,
                    employer_eps DOUBLE PRECISION DEFAULT 0,
                    employer_edli DOUBLE PRECISION DEFAULT 0,
                    employer_admin_charges DOUBLE PRECISION DEFAULT 0,
                    employer_pf_total DOUBLE PRECISION DEFAULT 0,

                    is_pwd INTEGER DEFAULT 0,
                    esic_if_applicable TEXT CHECK(esic_if_applicable IN ('Yes', 'No')) DEFAULT 'No',
                    esic_wage_ceiling_used DOUBLE PRECISION DEFAULT 0,
                    esic_eligible_by_wage INTEGER DEFAULT 0,
                    employer_esic DOUBLE PRECISION DEFAULT 0,
                    employee_esic DOUBLE PRECISION DEFAULT 0,

                    food_reimbursement TEXT CHECK(food_reimbursement IN ('Yes', 'No')) DEFAULT 'No',
                    ctc DOUBLE PRECISION DEFAULT 0,

                    leave_balance DOUBLE PRECISION DEFAULT 12,
                    status TEXT DEFAULT 'Active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS leave_requests (
                    id SERIAL PRIMARY KEY,
                    employee_code TEXT NOT NULL,
                    leave_type TEXT,
                    from_date TEXT,
                    to_date TEXT,
                    days DOUBLE PRECISION,
                    reason TEXT,
                    status TEXT DEFAULT 'Pending',
                    boss_employee_code TEXT,
                    decided_by TEXT,
                    decided_at TIMESTAMP,
                    applied_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (employee_code) REFERENCES employees(employee_code) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS announcements (
                    id SERIAL PRIMARY KEY,
                    title TEXT,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS leave_balances (
                    id SERIAL PRIMARY KEY,
                    employee_code TEXT NOT NULL,
                    leave_type TEXT NOT NULL,
                    balance DOUBLE PRECISION DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(employee_code, leave_type)
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    recipient_code TEXT NOT NULL,
                    title TEXT,
                    message TEXT,
                    related_type TEXT,
                    related_id INTEGER,
                    is_read INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS payroll_records (
                    id SERIAL PRIMARY KEY,
                    employee_code TEXT NOT NULL,
                    month INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    basic_pay DOUBLE PRECISION DEFAULT 0,
                    da DOUBLE PRECISION DEFAULT 0,
                    hra DOUBLE PRECISION DEFAULT 0,
                    phonebill_pay DOUBLE PRECISION DEFAULT 0,
                    others DOUBLE PRECISION DEFAULT 0,
                    gross DOUBLE PRECISION DEFAULT 0,
                    employee_pf DOUBLE PRECISION DEFAULT 0,
                    employee_esic DOUBLE PRECISION DEFAULT 0,
                    employer_pf_total DOUBLE PRECISION DEFAULT 0,
                    employer_esic DOUBLE PRECISION DEFAULT 0,
                    ctc DOUBLE PRECISION DEFAULT 0,
                    net_pay DOUBLE PRECISION DEFAULT 0,
                    lop_days DOUBLE PRECISION DEFAULT 0,
                    lop_amount DOUBLE PRECISION DEFAULT 0,
                    extra_days DOUBLE PRECISION DEFAULT 0,
                    extra_amount DOUBLE PRECISION DEFAULT 0,
                    per_day_rate DOUBLE PRECISION DEFAULT 0,
                    present_days DOUBLE PRECISION DEFAULT 0,
                    source TEXT DEFAULT 'manual',
                    generated_by TEXT,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(employee_code, month, year)
                );

                CREATE TABLE IF NOT EXISTS lop_extra_records (
                    id SERIAL PRIMARY KEY,
                    employee_code TEXT NOT NULL,
                    record_type TEXT NOT NULL CHECK(record_type IN ('LOP', 'EXTRA')),
                    record_date TEXT NOT NULL,
                    day_count DOUBLE PRECISION NOT NULL DEFAULT 1,
                    reason TEXT,
                    month INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (employee_code) REFERENCES employees(employee_code) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS attendance_records (
                    id SERIAL PRIMARY KEY,
                    employee_code TEXT NOT NULL,
                    month INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    day INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(employee_code, month, year, day)
                );
            """)

            cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin';")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, full_name) VALUES (%s, %s, %s, %s);",
                    (_normalize_username("admin"), hash_password("admin123"), "admin", "HR Administrator")
                )
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        release_connection(conn)

# ---------------------------------------------------------------------------
# AUTHENTICATION
# ---------------------------------------------------------------------------
def authenticate_user(username: str, password: str):
    uname = _normalize_username(username)
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE username = %s LIMIT 1;", (uname,))
            row = cur.fetchone()
            if not row:
                return None
            valid, legacy = verify_password(password, row["password_hash"])
            if not valid:
                return None
            if legacy:
                cur.execute("UPDATE users SET password_hash = %s WHERE id = %s;", (hash_password(password), row["id"]))
                conn.commit()
            return dict(row)
    finally:
        release_connection(conn)

def create_user(username, password, role, employee_code=None, full_name=None):
    conn = get_connection()
    uname = _normalize_username(username)
    code = _normalize_employee_code(employee_code) if employee_code else None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, role, employee_code, full_name) VALUES (%s, %s, %s, %s, %s);",
                (uname, hash_password(password), role, code, full_name)
            )
            conn.commit()
            return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False
    finally:
        release_connection(conn)

def username_exists(username: str) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE username = %s LIMIT 1;", (_normalize_username(username),))
            return cur.fetchone() is not None
    finally:
        release_connection(conn)

def change_password(username: str, new_password: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s;",
                (hash_password(new_password), _normalize_username(username))
            )
            conn.commit()
    finally:
        release_connection(conn)

def get_user_by_employee_code(employee_code: str, role: str = "employee"):
    conn = get_connection()
    code = _normalize_employee_code(employee_code)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM users WHERE LOWER(TRIM(employee_code)) = LOWER(%s) AND role = %s ORDER BY id DESC LIMIT 1;",
                (code, role)
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        release_connection(conn)

def reset_employee_password(employee_code: str, new_password: str):
    code = _normalize_employee_code(employee_code)
    if not code or not _clean_password(new_password):
        return None

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT employee_code, employee_name FROM employees WHERE LOWER(TRIM(employee_code)) = LOWER(%s) LIMIT 1;", (code,))
            emp = cur.fetchone()
            if not emp:
                return None

            cur.execute("SELECT * FROM users WHERE LOWER(TRIM(employee_code)) = LOWER(%s) AND role = 'employee' ORDER BY id DESC LIMIT 1;", (code,))
            user = cur.fetchone()
            if user:
                username = _normalize_username(user["username"])
                cur.execute(
                    "UPDATE users SET username = %s, password_hash = %s, full_name = %s, employee_code = %s WHERE id = %s;",
                    (username, hash_password(new_password), emp["employee_name"], code, user["id"])
                )
            else:
                username = _normalize_username(code)
                cur.execute("SELECT id FROM users WHERE username = %s LIMIT 1;", (username,))
                if cur.fetchone():
                    return None
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, employee_code, full_name) VALUES (%s, %s, 'employee', %s, %s);",
                    (username, hash_password(new_password), code, emp["employee_name"])
                )
            conn.commit()
            return username
    except Exception:
        conn.rollback()
        return None
    finally:
        release_connection(conn)

def get_database_info():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users;")
            u_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM employees;")
            e_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users WHERE role='employee';")
            el_count = cur.fetchone()[0]
            return {
                "path": "PostgreSQL Remote DB",
                "user_count": u_count,
                "employee_count": e_count,
                "employee_login_count": el_count,
            }
    finally:
        release_connection(conn)

def delete_user_login(username: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s;", (_normalize_username(username),))
            conn.commit()
    finally:
        release_connection(conn)

# ---------------------------------------------------------------------------
# CTC CALCULATIONS
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
    if "employee_code" in data:
        data["employee_code"] = _normalize_employee_code(data["employee_code"])
    cols = list(data.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    col_names = ", ".join(cols)
    try:
        with conn.cursor() as cur:
            cur.execute(f"INSERT INTO employees ({col_names}) VALUES ({placeholders});", list(data.values()))
            conn.commit()
            return True
    except Exception:
        conn.rollback()
        return False
    finally:
        release_connection(conn)

def update_employee(employee_code: str, data: dict):
    code = _normalize_employee_code(employee_code)
    conn = get_connection()
    data["updated_at"] = datetime.now()
    set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE employees SET {set_clause} WHERE LOWER(TRIM(employee_code)) = LOWER(%s);", list(data.values()) + [code])
            conn.commit()
            return True
    except Exception:
        conn.rollback()
        return False
    finally:
        release_connection(conn)

def delete_employee(employee_code: str):
    code = _normalize_employee_code(employee_code)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employees WHERE LOWER(TRIM(employee_code)) = LOWER(%s);", (code,))
            cur.execute("DELETE FROM users WHERE LOWER(TRIM(employee_code)) = LOWER(%s);", (code,))
            cur.execute("DELETE FROM leave_balances WHERE LOWER(TRIM(employee_code)) = LOWER(%s);", (code,))
            conn.commit()
    finally:
        release_connection(conn)

def get_all_employees():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM employees ORDER BY created_at DESC;")
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

def get_employee(employee_code: str):
    code = _normalize_employee_code(employee_code)
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM employees WHERE LOWER(TRIM(employee_code)) = LOWER(%s);", (code,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        release_connection(conn)

def employee_count():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM employees;")
            return cur.fetchone()[0]
    finally:
        release_connection(conn)

def next_employee_code():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT employee_code FROM employees;")
            rows = cur.fetchall()
            nums = []
            for (code,) in rows:
                if code and "-" in code:
                    try:
                        nums.append(int(code.split("-")[-1]))
                    except ValueError:
                        pass
            next_id = max(nums) + 1 if nums else 1
            return f"TT-EMP-{next_id:04d}"
    finally:
        release_connection(conn)

def get_all_employee_names():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT employee_code, employee_name FROM employees ORDER BY employee_name;")
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

def get_employees_reporting_to(boss_code: str):
    if not boss_code:
        return []
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM employees WHERE LOWER(TRIM(reporting_boss_code)) = LOWER(%s) ORDER BY employee_name;",
                (_normalize_employee_code(boss_code),)
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

def get_statutory_summary():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
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
                FROM employees WHERE status = 'Active';
            """)
            row = cur.fetchone()
            return dict(row) if row else {}
    finally:
        release_connection(conn)

# ---------------------------------------------------------------------------
# LEAVE BALANCES
# ---------------------------------------------------------------------------
def upsert_leave_balance(employee_code: str, leave_type: str, balance: float):
    code = _normalize_employee_code(employee_code)
    ltype = (leave_type or "").strip().upper()
    if not code or ltype not in LEAVE_TYPES:
        return False
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO leave_balances (employee_code, leave_type, balance, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (employee_code, leave_type)
                DO UPDATE SET balance = EXCLUDED.balance, updated_at = CURRENT_TIMESTAMP;
            """, (code, ltype, float(balance)))
            conn.commit()
            return True
    except Exception:
        conn.rollback()
        return False
    finally:
        release_connection(conn)

def bulk_upsert_leave_balances(rows):
    ok, failed = 0, 0
    touched_codes = set()
    for r in rows:
        code = _normalize_employee_code(r.get("employee_code", ""))
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
            touched_codes.add(code)
        else:
            failed += 1

    for code in touched_codes:
        create_notification(
            code, "Leave Balance Updated",
            "HR has updated your leave balance. Please check the Leave tab for your latest CL/SL/PL balance.",
            "leave_balance", None,
        )
    return ok, failed

def get_leave_balances(employee_code: str):
    code = _normalize_employee_code(employee_code)
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM leave_balances WHERE LOWER(TRIM(employee_code)) = LOWER(%s) ORDER BY leave_type;", (code,))
            existing = {r["leave_type"]: dict(r) for r in cur.fetchall()}
            out = []
            for lt in LEAVE_TYPES:
                if lt in existing:
                    out.append(existing[lt])
                else:
                    out.append({"employee_code": code, "leave_type": lt, "balance": 0.0, "updated_at": None})
            return out
    finally:
        release_connection(conn)

def get_leave_balance_map(employee_code: str):
    return {b["leave_type"]: b["balance"] for b in get_leave_balances(employee_code)}

def get_all_leave_balances():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM leave_balances ORDER BY employee_code, leave_type;")
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

def adjust_leave_balance(employee_code: str, leave_type: str, delta: float):
    current = get_leave_balance_map(employee_code).get(leave_type, 0.0)
    upsert_leave_balance(employee_code, leave_type, current + delta)

# ---------------------------------------------------------------------------
# LEAVE REQUEST WORKFLOW
# ---------------------------------------------------------------------------
def apply_leave(employee_code, leave_type, from_date, to_date, days, reason):
    code = _normalize_employee_code(employee_code)
    emp = get_employee(code)
    if not emp:
        return False, "Employee record not found."
    if emp.get("employee_type") != "Permanent":
        return False, "Only Permanent employees are eligible to apply for leave. Probation employees are not entitled to paid leave."

    ltype = (leave_type or "").strip().upper()
    if ltype not in LEAVE_TYPES:
        return False, "Invalid leave type."

    balance = get_leave_balance_map(code).get(ltype, 0.0)
    if float(days) > balance:
        return False, f"Insufficient {LEAVE_TYPE_LABELS[ltype]} balance. Available: {balance:g} day(s), requested: {days:g} day(s)."

    boss_code = _normalize_employee_code(emp.get("reporting_boss_code")) or None

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO leave_requests (employee_code, leave_type, from_date, to_date, days, reason, boss_employee_code)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
            """, (code, ltype, str(from_date), str(to_date), days, reason, boss_code))
            request_id = cur.fetchone()[0]
            conn.commit()
    finally:
        release_connection(conn)

    emp_name = emp.get("employee_name", code)
    msg = f"{emp_name} ({code}) applied for {LEAVE_TYPE_LABELS.get(ltype, ltype)} from {from_date} to {to_date} ({days:g} day(s))."
    if boss_code:
        create_notification(boss_code, "New Leave Request", msg, "leave_request", request_id)
    create_notification("ADMIN", "New Leave Request", msg, "leave_request", request_id)

    return True, "Leave request submitted successfully."

def get_leave_requests(employee_code=None, boss_employee_code=None, status=None):
    conn = get_connection()
    query = "SELECT * FROM leave_requests WHERE 1=1"
    params = []
    if employee_code:
        query += " AND LOWER(TRIM(employee_code)) = LOWER(%s)"
        params.append(_normalize_employee_code(employee_code))
    if boss_employee_code:
        query += " AND LOWER(TRIM(boss_employee_code)) = LOWER(%s)"
        params.append(_normalize_employee_code(boss_employee_code))
    if status:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY applied_on DESC;"
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

def get_leave_request_counts(employee_code=None, boss_employee_code=None):
    reqs = get_leave_requests(employee_code=employee_code, boss_employee_code=boss_employee_code)
    counts = {"Pending": 0, "Approved": 0, "Rejected": 0}
    for r in reqs:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts

def decide_leave(request_id: int, status: str, decided_by: str = None):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM leave_requests WHERE id = %s;", (request_id,))
            row = cur.fetchone()
            if not row:
                return False
            req = dict(row)

            cur.execute(
                "UPDATE leave_requests SET status = %s, decided_by = %s, decided_at = CURRENT_TIMESTAMP WHERE id = %s;",
                (status, decided_by, request_id)
            )
            conn.commit()
    finally:
        release_connection(conn)

    if status == "Approved":
        adjust_leave_balance(req["employee_code"], req["leave_type"], -float(req["days"] or 0))

    decider_label = decided_by or ("HR/Admin" if not req.get("boss_employee_code") else "your reporting manager")
    ltype_label = LEAVE_TYPE_LABELS.get(req["leave_type"], req["leave_type"])
    msg = f"Your {ltype_label} request ({req['from_date']} to {req['to_date']}, {req['days']:g} day(s)) was {status.lower()} by {decider_label}."
    create_notification(req["employee_code"], f"Leave {status}", msg, "leave_request", request_id)

    emp_row = get_employee(req["employee_code"])
    emp_name = emp_row.get("employee_name", req["employee_code"]) if emp_row else req["employee_code"]
    admin_msg = f"{emp_name} ({req['employee_code']})'s {ltype_label} request ({req['from_date']} to {req['to_date']}) was {status.upper()} by {decided_by or 'HR/Admin'}."
    create_notification("ADMIN", f"Leave {status}", admin_msg, "leave_request", request_id)

    boss_code = req.get("boss_employee_code")
    if boss_code and _normalize_employee_code(boss_code) != _normalize_employee_code(decided_by or ""):
        boss_msg = f"{emp_name} ({req['employee_code']})'s {ltype_label} request ({req['from_date']} to {req['to_date']}) was {status.upper()} by {decided_by or 'HR/Admin'}."
        create_notification(boss_code, f"Team Leave {status}", boss_msg, "leave_request", request_id)

    return True

# ---------------------------------------------------------------------------
# NOTIFICATIONS & ANNOUNCEMENTS
# ---------------------------------------------------------------------------
def create_notification(recipient_code, title, message, related_type=None, related_id=None):
    conn = get_connection()
    recipient = (recipient_code or "").strip()
    recipient = "ADMIN" if recipient.upper() == "ADMIN" else _normalize_employee_code(recipient)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO notifications (recipient_code, title, message, related_type, related_id)
                VALUES (%s, %s, %s, %s, %s);
            """, (recipient, title, message, related_type, related_id))
            conn.commit()
    finally:
        release_connection(conn)

def get_notifications(recipient_code, unread_only=False, limit=30):
    conn = get_connection()
    recipient = (recipient_code or "").strip()
    recipient = "ADMIN" if recipient.upper() == "ADMIN" else _normalize_employee_code(recipient)
    query = "SELECT * FROM notifications WHERE recipient_code = %s"
    params = [recipient]
    if unread_only:
        query += " AND is_read = 0"
    query += " ORDER BY created_at DESC LIMIT %s;"
    params.append(limit)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

def get_notification_log(recipient_code="ADMIN", related_type=None, limit=500):
    conn = get_connection()
    recipient = (recipient_code or "").strip()
    recipient = "ADMIN" if recipient.upper() == "ADMIN" else _normalize_employee_code(recipient)
    query = "SELECT * FROM notifications WHERE recipient_code = %s"
    params = [recipient]
    if related_type:
        query += " AND related_type = %s"
        params.append(related_type)
    query += " ORDER BY created_at DESC LIMIT %s;"
    params.append(limit)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

def unread_notification_count(recipient_code):
    conn = get_connection()
    recipient = (recipient_code or "").strip()
    recipient = "ADMIN" if recipient.upper() == "ADMIN" else _normalize_employee_code(recipient)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM notifications WHERE recipient_code = %s AND is_read = 0;", (recipient,))
            return cur.fetchone()[0]
    finally:
        release_connection(conn)

def mark_notification_read(notification_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE notifications SET is_read = 1 WHERE id = %s;", (notification_id,))
            conn.commit()
    finally:
        release_connection(conn)

def mark_all_notifications_read(recipient_code):
    conn = get_connection()
    recipient = (recipient_code or "").strip()
    recipient = "ADMIN" if recipient.upper() == "ADMIN" else _normalize_employee_code(recipient)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE notifications SET is_read = 1 WHERE recipient_code = %s;", (recipient,))
            conn.commit()
    finally:
        release_connection(conn)

def add_announcement(title, message):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO announcements (title, message) VALUES (%s, %s);", (title, message))
            conn.commit()
    finally:
        release_connection(conn)

def get_announcements(limit=10):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM announcements ORDER BY created_at DESC LIMIT %s;", (limit,))
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

# ---------------------------------------------------------------------------
# LOSS OF PAY (LOP) / EXTRA DAYS (LEGACY)
# ---------------------------------------------------------------------------
def add_lop_extra_record(employee_code, record_type, record_date, day_count, reason="", created_by=None):
    code = _normalize_employee_code(employee_code)
    rtype = (record_type or "").strip().upper()
    if not code or rtype not in LOP_EXTRA_TYPES:
        return False
    try:
        days = float(day_count)
        if days <= 0:
            return False
        rdate = str(record_date)
        y, m = int(rdate[0:4]), int(rdate[5:7])
    except Exception:
        return False

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO lop_extra_records
                (employee_code, record_type, record_date, day_count, reason, month, year, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (code, rtype, rdate, days, reason, m, y, created_by))
            conn.commit()
            return True
    finally:
        release_connection(conn)

def bulk_upsert_lop_extra(rows, record_type, created_by=None):
    ok, failed = 0, 0
    for r in rows:
        code = _normalize_employee_code(r.get("employee_code", ""))
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
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lop_extra_records WHERE id = %s;", (record_id,))
            conn.commit()
    finally:
        release_connection(conn)

def get_lop_extra_records(employee_code=None, month=None, year=None, record_type=None):
    conn = get_connection()
    query = "SELECT * FROM lop_extra_records WHERE 1=1"
    params = []
    if employee_code:
        query += " AND LOWER(TRIM(employee_code)) = LOWER(%s)"
        params.append(_normalize_employee_code(employee_code))
    if month:
        query += " AND month = %s"
        params.append(month)
    if year:
        query += " AND year = %s"
        params.append(year)
    if record_type:
        query += " AND record_type = %s"
        params.append(record_type.upper())
    query += " ORDER BY record_date DESC;"
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

def get_lop_extra_summary(employee_code: str, month: int, year: int):
    code = _normalize_employee_code(employee_code)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(day_count), 0) FROM lop_extra_records
                WHERE LOWER(TRIM(employee_code)) = LOWER(%s) AND month = %s AND year = %s AND record_type = 'LOP';
            """, (code, month, year))
            lop = cur.fetchone()[0] or 0.0

            cur.execute("""
                SELECT COALESCE(SUM(day_count), 0) FROM lop_extra_records
                WHERE LOWER(TRIM(employee_code)) = LOWER(%s) AND month = %s AND year = %s AND record_type = 'EXTRA';
            """, (code, month, year))
            extra = cur.fetchone()[0] or 0.0
            return {"lop_days": float(lop), "extra_days": float(extra)}
    finally:
        release_connection(conn)

# ---------------------------------------------------------------------------
# ATTENDANCE ENGINE
# ---------------------------------------------------------------------------
def upsert_attendance_day(employee_code, month, year, day, status, created_by=None):
    code = _normalize_employee_code(employee_code)
    status = (status or "").strip().upper()
    if not code or status not in ATTENDANCE_STATUS_CODES:
        return False
    try:
        day, month, year = int(day), int(month), int(year)
        if not (1 <= day <= 31):
            return False
    except (TypeError, ValueError):
        return False

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO attendance_records (employee_code, month, year, day, status, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(employee_code, month, year, day) DO UPDATE SET
                    status = EXCLUDED.status,
                    created_by = EXCLUDED.created_by,
                    created_at = CURRENT_TIMESTAMP;
            """, (code, month, year, day, status, created_by))
            conn.commit()
            return True
    except Exception:
        conn.rollback()
        return False
    finally:
        release_connection(conn)

def bulk_upsert_attendance(rows, month, year, created_by=None, day_columns=None):
    if day_columns is None:
        day_columns = [str(d) for d in range(1, 32)]
    employees_processed, applied, failed = 0, 0, 0
    for r in rows:
        code = _normalize_employee_code(r.get("employee_code", ""))
        if not code or not get_employee(code):
            failed += len(day_columns)
            continue
        any_cell = False
        for dcol in day_columns:
            raw = r.get(dcol)
            if raw is None:
                continue
            status = str(raw).strip().upper()
            if not status or status in ("NAN", "NONE"):
                continue
            try:
                day_num = int(float(dcol))
            except ValueError:
                continue
            if status not in ATTENDANCE_STATUS_CODES:
                failed += 1
                continue
            if upsert_attendance_day(code, month, year, day_num, status, created_by):
                applied += 1
                any_cell = True
            else:
                failed += 1
        if any_cell:
            employees_processed += 1
    return employees_processed, applied, failed

def get_attendance_records(employee_code=None, month=None, year=None):
    conn = get_connection()
    query = "SELECT * FROM attendance_records WHERE 1=1"
    params = []
    if employee_code:
        query += " AND LOWER(TRIM(employee_code)) = LOWER(%s)"
        params.append(_normalize_employee_code(employee_code))
    if month:
        query += " AND month = %s"
        params.append(month)
    if year:
        query += " AND year = %s"
        params.append(year)
    query += " ORDER BY employee_code, day;"
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)

def has_attendance_for_month(employee_code, month, year):
    code = _normalize_employee_code(employee_code)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM attendance_records WHERE LOWER(TRIM(employee_code)) = LOWER(%s) AND month = %s AND year = %s;", (code, month, year))
            return cur.fetchone()[0] > 0
    finally:
        release_connection(conn)

def get_attendance_summary(employee_code, month, year):
    recs = get_attendance_records(employee_code, month, year)
    present = sum(1 for r in recs if r["status"] in PRESENT_CODES)
    absent = sum(1 for r in recs if r["status"] in LOP_FULL_CODES)
    half = sum(1 for r in recs if r["status"] in LOP_HALF_CODES)
    extra = sum(1 for r in recs if r["status"] in EXTRA_CODES)
    week_off = sum(1 for r in recs if r["status"] == "WO")
    holiday = sum(1 for r in recs if r["status"] == "H")
    on_leave = sum(1 for r in recs if r["status"] == "PL")
    lop_days = absent + 0.5 * half
    return {
        "present_days": present,
        "absent_days": absent,
        "half_days": half,
        "extra_days": extra,
        "week_off_days": week_off,
        "holiday_days": holiday,
        "on_leave_days": on_leave,
        "lop_days": lop_days,
        "days_recorded": len(recs),
    }

def get_attendance_matrix(month, year):
    recs = get_attendance_records(month=month, year=year)
    by_emp = {}
    for r in recs:
        by_emp.setdefault(r["employee_code"], {})[r["day"]] = r["status"]
    out = []
    for code, days in by_emp.items():
        emp = get_employee(code)
        row = {
            "employee_code": code,
            "employee_name": emp.get("employee_name", "") if emp else "",
        }
        for d in range(1, 32):
            row[str(d)] = days.get(d, "")
        out.append(row)
    out.sort(key=lambda r: r["employee_code"])
    return out

def delete_attendance_month(month, year):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attendance_records WHERE month = %s AND year = %s;", (month, year))
            conn.commit()
    finally:
        release_connection(conn)

# ---------------------------------------------------------------------------
# PAYROLL RECORDS
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

def generate_payroll(employee_code: str, month: int, year: int, generated_by: str = None, notify: bool = False):
    code = _normalize_employee_code(employee_code)
    emp = get_employee(code)
    if not emp:
        return False
    snap = _snapshot_from_employee(emp)

    if has_attendance_for_month(code, month, year):
        att = get_attendance_summary(code, month, year)
        lop_days = att["lop_days"]
        extra_days = att["extra_days"]
        present_days = att["present_days"]
        source = "attendance"
    else:
        legacy = get_lop_extra_summary(code, month, year)
        lop_days = legacy["lop_days"]
        extra_days = legacy["extra_days"]
        present_days = 0
        source = "manual"

    per_day_rate = round(snap["gross"] / STANDARD_WORKING_DAYS, 2) if STANDARD_WORKING_DAYS else 0.0
    lop_amount = round(per_day_rate * lop_days, 2)
    extra_amount = round(per_day_rate * extra_days, 2)

    snap["lop_days"] = lop_days
    snap["lop_amount"] = lop_amount
    snap["extra_days"] = extra_days
    snap["extra_amount"] = extra_amount
    snap["per_day_rate"] = per_day_rate
    snap["present_days"] = present_days
    snap["source"] = source
    snap["net_pay"] = round(snap["net_pay"] - lop_amount + extra_amount, 2)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO payroll_records
                (employee_code, month, year, basic_pay, da, hra, phonebill_pay, others, gross,
                 employee_pf, employee_esic, employer_pf_total, employer_esic, ctc, net_pay,
                 lop_days, lop_amount, extra_days, extra_amount, per_day_rate, present_days, source,
                 generated_by, generated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CURRENT_TIMESTAMP)
                ON CONFLICT(employee_code, month, year) DO UPDATE SET
                    basic_pay=EXCLUDED.basic_pay, da=EXCLUDED.da, hra=EXCLUDED.hra,
                    phonebill_pay=EXCLUDED.phonebill_pay, others=EXCLUDED.others, gross=EXCLUDED.gross,
                    employee_pf=EXCLUDED.employee_pf, employee_esic=EXCLUDED.employee_esic,
                    employer_pf_total=EXCLUDED.employer_pf_total, employer_esic=EXCLUDED.employer_esic,
                    ctc=EXCLUDED.ctc, net_pay=EXCLUDED.net_pay,
                    lop_days=EXCLUDED.lop_days, lop_amount=EXCLUDED.lop_amount,
                    extra_days=EXCLUDED.extra_days, extra_amount=EXCLUDED.extra_amount,
                    per_day_rate=EXCLUDED.per_day_rate, present_days=EXCLUDED.present_days,
                    source=EXCLUDED.source,
                    generated_by=EXCLUDED.generated_by, generated_at=CURRENT_TIMESTAMP;
            """, (code, month, year, snap["basic_pay"], snap["da"], snap["hra"], snap["phonebill_pay"],
                  snap["others"], snap["gross"], snap["employee_pf"], snap["employee_esic"],
                  snap["employer_pf_total"], snap["employer_esic"], snap["ctc"], snap["net_pay"],
                  snap["lop_days"], snap["lop_amount"], snap["extra_days"], snap["extra_amount"],
                  snap["per_day_rate"], snap["present_days"], snap["source"], generated_by))
            conn.commit()
    finally:
        release_connection(conn)

    if notify:
        month_label = MONTH_NAMES[month - 1]
        create_notification(
            code, "Payslip Ready",
            f"Your payslip for {month_label} {year} has been generated. Net Pay: ₹{snap['net_pay']:,.0f}.",
            "payslip", None,
        )
    return True

def generate_payroll_for_all(month: int, year: int, generated_by: str = None, active_only=True, notify: bool = True):
    emps = get_all_employees()
    count = 0
    for e in emps:
        if active_only and e.get("status") != "Active":
            continue
        if generate_payroll(e["employee_code"], month, year, generated_by, notify=notify):
            count += 1
    return count

def get_payroll_record(employee_code: str, month: int, year: int):
    code = _normalize_employee_code(employee_code)
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM payroll_records WHERE LOWER(TRIM(employee_code)) = LOWER(%s) AND month = %s AND year = %s;", (code, month, year))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        release_connection(conn)

def get_payroll_months_for_employee(employee_code: str):
    code = _normalize_employee_code(employee_code)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT month, year FROM payroll_records WHERE LOWER(TRIM(employee_code)) = LOWER(%s) ORDER BY year DESC, month DESC;", (code,))
            return [(r[0], r[1]) for r in cur.fetchall()]
    finally:
        release_connection(conn)

def get_all_payroll_records(month=None, year=None, employee_code=None):
    conn = get_connection()
    query = "SELECT * FROM payroll_records WHERE 1=1"
    params = []
    if month:
        query += " AND month = %s"
        params.append(month)
    if year:
        query += " AND year = %s"
        params.append(year)
    if employee_code:
        query += " AND LOWER(TRIM(employee_code)) = LOWER(%s)"
        params.append(_normalize_employee_code(employee_code))
    query += " ORDER BY year DESC, month DESC, employee_code;"
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)