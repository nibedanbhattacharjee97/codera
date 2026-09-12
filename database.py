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
from datetime import datetime

# ---------------------------------------------------------------------------
# SINGLE SHARED DATABASE
# ---------------------------------------------------------------------------
# Both admin.py and employee_count.py must use the exact same database.
# A shared per-user location prevents the common production problem where
# Admin and Employee are launched from two copied project folders and silently
# use two different SQLite files. HRMS_DB_PATH can override this location.
LOCAL_DB_DIR = os.path.join(os.path.dirname(__file__), "database")
os.makedirs(LOCAL_DB_DIR, exist_ok=True)
LOCAL_DB_PATH = os.path.join(LOCAL_DB_DIR, "hr_system.db")
SHARED_DB_DIR = os.path.join(os.path.expanduser("~"), ".tec_taniva_hrms")
os.makedirs(SHARED_DB_DIR, exist_ok=True)
SHARED_DB_PATH = os.path.join(SHARED_DB_DIR, "hr_system.db")
DB_PATH = os.environ.get("HRMS_DB_PATH", SHARED_DB_PATH)

# On first migration, preserve an existing project database instead of
# starting with an empty shared database. This runs only when the shared DB
# does not exist yet.
if not os.path.exists(DB_PATH) and DB_PATH == SHARED_DB_PATH and os.path.exists(LOCAL_DB_PATH):
    try:
        import shutil
        shutil.copy2(LOCAL_DB_PATH, DB_PATH)
    except OSError:
        pass

# ---------------------------------------------------------------------------
# STATUTORY CONSTANTS (India - PF & ESI, FY 2026)
# ---------------------------------------------------------------------------
PF_WAGE_CEILING = 15000.0       # Statutory PF wage ceiling (Rs./month)
EPF_EMPLOYEE_RATE = 0.12        # Employee share -> EPF account (on PF wage per basis)
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

PF_BASIS_OPTIONS = ["capped", "actual"]


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _normalize_username(username: str) -> str:
    """Login usernames are matched case-insensitively and with surrounding
    whitespace stripped, so a stray space or different capitalization typed
    on a phone keyboard never silently breaks a login."""
    return (username or "").strip().lower()


def _clean_password(password: str) -> str:
    return (password or "").strip()


def hash_password(password: str) -> str:
    """Create a strong password hash.

    New accounts use PBKDF2-HMAC-SHA256 with a random salt. Legacy plain
    SHA-256 hashes remain readable by verify_password() so existing users are
    not locked out.
    """
    raw = _clean_password(password).encode("utf-8")
    salt = secrets.token_bytes(16)
    iterations = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", raw, salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """Return (valid, was_legacy_sha256)."""
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

    # Legacy database compatibility.
    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, stored_hash), True


def _ensure_column(cur, table, column, coltype_and_default):
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype_and_default}")


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

    # --- Fully Patched Schema Migration Loop ---
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
    ]:
        _ensure_column(cur, "employees", col, decl)
    conn.commit()

    # --- Username normalization migration ---
    # Older rows may have been stored with mixed case / stray whitespace
    # from before usernames were normalized. Normalize them in place so
    # logins created before this fix don't suddenly break.
    cur.execute("SELECT id, username FROM users")
    for row in cur.fetchall():
        normalized = _normalize_username(row["username"])
        if normalized != row["username"]:
            cur.execute("UPDATE users SET username = ? WHERE id = ?", (normalized, row["id"]))
    conn.commit()

    # Seed Default Admin
    cur.execute("SELECT COUNT(*) as c FROM users WHERE role = 'admin'")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
            (_normalize_username("admin"), hash_password("admin123"), "admin", "HR Administrator"),
        )
        conn.commit()

    conn.close()


def authenticate_user(username: str, password: str):
    """Authenticate against the shared DB and transparently upgrade legacy hashes."""
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
        # Upgrade old SHA-256 records after a successful login.
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
    """Look up the portal login (if any) already tied to an employee code.
    Used by the admin Portal Access tab so a second attempt updates the
    existing account instead of failing with 'username already taken'."""
    conn = get_connection()
    code = (employee_code or "").strip()
    row = conn.execute(
        "SELECT * FROM users WHERE lower(trim(employee_code)) = lower(?) AND role = ? ORDER BY id DESC LIMIT 1",
        (code, role),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def reset_employee_password(employee_code: str, new_password: str):
    """Create or reset the one-to-one employee portal login.

    This deliberately repairs a broken/missing portal record instead of
    showing credentials that are not actually present in the database.
    """
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
        # If the preferred username is already used by another account, fail
        # rather than creating a login that cannot be uniquely identified.
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