"""Production-ready SQLite data layer for TEC TANIVA HRMS."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "hr_system.db")

# India payroll constants. Review with payroll/legal team before production use.
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

PASSWORD_SCHEME = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 310_000


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 20000")
    return conn


def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def hash_password(password: str) -> str:
    """PBKDF2 password hash with a random salt."""
    if password is None:
        password = ""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PASSWORD_SCHEME}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Return (valid, legacy_sha256). Supports old SHA-256 rows for migration."""
    if not stored:
        return False, False
    if stored.startswith(PASSWORD_SCHEME + "$"):
        try:
            _, iterations, salt_hex, digest_hex = stored.split("$", 3)
            iterations = int(iterations)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            actual = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, iterations)
            return hmac.compare_digest(actual, expected), False
        except (ValueError, TypeError):
            return False, False
    # Backward compatibility with the old application.
    legacy = hashlib.sha256((password or "").strip().encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, stored), True


def _ensure_column(cur, table: str, column: str, declaration: str) -> None:
    existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin','employee')),
        employee_code TEXT,
        full_name TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
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
        employee_type TEXT CHECK(employee_type IN ('Probation','Permanent')),
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
        pf_basis TEXT DEFAULT 'capped',
        pf_wage REAL DEFAULT 0,
        pf REAL DEFAULT 0,
        employer_pf REAL DEFAULT 0,
        employer_eps REAL DEFAULT 0,
        employer_edli REAL DEFAULT 0,
        employer_admin_charges REAL DEFAULT 0,
        employer_pf_total REAL DEFAULT 0,
        is_pwd INTEGER DEFAULT 0,
        esic_if_applicable TEXT DEFAULT 'No',
        esic_wage_ceiling_used REAL DEFAULT 0,
        esic_eligible_by_wage INTEGER DEFAULT 0,
        employer_esic REAL DEFAULT 0,
        employee_esic REAL DEFAULT 0,
        food_reimbursement TEXT DEFAULT 'No',
        ctc REAL DEFAULT 0,
        leave_balance REAL DEFAULT 12,
        status TEXT DEFAULT 'Active',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_code TEXT NOT NULL,
        leave_type TEXT NOT NULL,
        from_date TEXT NOT NULL,
        to_date TEXT NOT NULL,
        days REAL NOT NULL,
        reason TEXT,
        status TEXT DEFAULT 'Pending',
        applied_on TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(employee_code) REFERENCES employees(employee_code) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        message TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Safe migrations for databases created by previous versions.
    migrations = [
        ("da", "REAL DEFAULT 0"), ("pf_basis", "TEXT DEFAULT 'capped'"),
        ("pf_wage", "REAL DEFAULT 0"), ("pf", "REAL DEFAULT 0"),
        ("employer_pf", "REAL DEFAULT 0"), ("employer_eps", "REAL DEFAULT 0"),
        ("employer_edli", "REAL DEFAULT 0"), ("employer_admin_charges", "REAL DEFAULT 0"),
        ("employer_pf_total", "REAL DEFAULT 0"), ("is_pwd", "INTEGER DEFAULT 0"),
        ("esic_wage_ceiling_used", "REAL DEFAULT 0"), ("esic_eligible_by_wage", "INTEGER DEFAULT 0"),
        ("employer_esic", "REAL DEFAULT 0"), ("employee_esic", "REAL DEFAULT 0"),
        ("food_reimbursement", "TEXT DEFAULT 'No'"), ("leave_balance", "REAL DEFAULT 12"),
        ("status", "TEXT DEFAULT 'Active'"), ("updated_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
    ]
    for col, decl in migrations:
        _ensure_column(cur, "employees", col, decl)

    # Normalize old usernames without creating collisions.
    rows = cur.execute("SELECT id, username FROM users").fetchall()
    for row in rows:
        normalized = _normalize_username(row["username"])
        if normalized != row["username"]:
            try:
                cur.execute("UPDATE users SET username=? WHERE id=?", (normalized, row["id"]))
            except sqlite3.IntegrityError:
                pass

    # Ensure a usable admin account exists on a fresh deployment.
    # Existing admin accounts are NEVER overwritten.
    admin = cur.execute("SELECT id, password_hash FROM users WHERE username='admin' AND role='admin'").fetchone()
    if admin is None:
        default_admin_password = os.getenv("HRMS_ADMIN_PASSWORD", "admin123")
        if len(default_admin_password) < 8:
            default_admin_password = "admin123"
        cur.execute(
            "INSERT INTO users(username,password_hash,role,full_name) VALUES(?,?,?,?)",
            ("admin", hash_password(default_admin_password), "admin", "System Administrator"),
        )

    conn.commit()
    conn.close()


def authenticate_user(username: str, password: str):
    uname = _normalize_username(username)
    if not uname or password is None:
        return None
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE username=?", (uname,)).fetchone()
    if not row:
        conn.close()
        return None
    valid, legacy = _verify_password(password, row["password_hash"])
    if not valid:
        conn.close()
        return None
    if legacy:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), row["id"]))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
    result = dict(row)
    conn.close()
    return result


def create_user(username, password, role, employee_code=None, full_name=None):
    uname = _normalize_username(username)
    if not uname or not password or role not in {"admin", "employee"}:
        return False
    if role == "employee" and not employee_code:
        return False
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users(username,password_hash,role,employee_code,full_name) VALUES(?,?,?,?,?)",
            (uname, hash_password(password), role, employee_code, full_name),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def username_exists(username: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM users WHERE username=?", (_normalize_username(username),)).fetchone()
    conn.close()
    return row is not None


def change_password(username: str, new_password: str) -> bool:
    if len(new_password or "") < 8:
        return False
    conn = get_connection()
    cur = conn.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(new_password), _normalize_username(username)))
    conn.commit()
    ok = cur.rowcount == 1
    conn.close()
    return ok


def get_user_by_employee_code(employee_code: str, role: str = "employee"):
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE employee_code=? AND role=? ORDER BY id DESC LIMIT 1", (employee_code, role)).fetchone()
    conn.close()
    return dict(row) if row else None


def reset_employee_password(employee_code: str, new_password: str):
    user = get_user_by_employee_code(employee_code, "employee")
    if not user or len(new_password or "") < 8:
        return None
    return user["username"] if change_password(user["username"], new_password) else None


def delete_user_login(username: str):
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE username=?", (_normalize_username(username),))
    conn.commit(); conn.close()


def calculate_ctc(basic, da, hra, phonebill, others, esic_if_applicable, pf_basis="capped", is_pwd=False):
    b, d, h, p, o = [max(0.0, float(x or 0)) for x in (basic, da, hra, phonebill, others)]
    pf_basis = pf_basis if pf_basis in PF_BASIS_OPTIONS else "capped"
    pf_wage_base = b + d
    gross = pf_wage_base + h + p + o
    pf_wage = min(pf_wage_base, PF_WAGE_CEILING) if pf_basis == "capped" else pf_wage_base
    employee_pf = round(pf_wage * EPF_EMPLOYEE_RATE, 2)
    employer_12 = round(pf_wage * EMPLOYER_PF_TOTAL_RATE, 2)
    eps_wage = min(pf_wage, PF_WAGE_CEILING)
    employer_eps = round(min(eps_wage * EPS_EMPLOYER_RATE, EPS_MAX_MONTHLY), 2)
    employer_epf = round(employer_12 - employer_eps, 2)
    employer_edli = round(min(pf_wage * EDLI_EMPLOYER_RATE, EDLI_MAX_MONTHLY), 2)
    employer_admin = round(pf_wage * PF_ADMIN_CHARGE_RATE, 2)
    employer_pf_total = round(employer_epf + employer_eps + employer_edli + employer_admin, 2)
    esi_ceiling = ESI_WAGE_CEILING_PWD if is_pwd else ESI_WAGE_CEILING_STANDARD
    eligible = esic_if_applicable == "Yes" and gross <= esi_ceiling
    employer_esic = round(gross * ESI_EMPLOYER_RATE, 2) if eligible else 0.0
    employee_esic = round(gross * ESI_EMPLOYEE_RATE, 2) if eligible else 0.0
    total_ctc = round(gross + employer_pf_total + employer_esic, 2)
    return total_ctc, {
        "gross": round(gross,2), "pf_basis": pf_basis, "pf_wage_base": round(pf_wage_base,2),
        "pf_wage": round(pf_wage,2), "employee_pf": employee_pf, "employer_epf": employer_epf,
        "employer_eps": employer_eps, "employer_edli": employer_edli, "employer_admin_charges": employer_admin,
        "employer_pf_total": employer_pf_total, "esi_ceiling": esi_ceiling, "esic_eligible": eligible,
        "employer_esic": employer_esic, "employee_esic": employee_esic, "total_ctc": total_ctc,
    }


def add_employee(data: dict):
    if not data.get("employee_code") or not data.get("employee_name"):
        return False
    conn = get_connection()
    try:
        cols = list(data.keys())
        conn.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", [data[c] for c in cols])
        conn.commit(); return True
    except sqlite3.IntegrityError:
        return False
    finally: conn.close()


def update_employee(employee_code: str, data: dict):
    if not data: return False
    data = dict(data)
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        cols = list(data.keys())
        conn.execute(f"UPDATE employees SET {','.join(f'{c}=?' for c in cols)} WHERE employee_code=?", [data[c] for c in cols] + [employee_code])
        conn.commit(); return True
    except Exception:
        return False
    finally: conn.close()


def delete_employee(employee_code: str):
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE employee_code=?", (employee_code,))
    conn.execute("DELETE FROM employees WHERE employee_code=?", (employee_code,))
    conn.commit(); conn.close()


def get_all_employees():
    conn = get_connection(); rows = conn.execute("SELECT * FROM employees ORDER BY created_at DESC, employee_name").fetchall(); conn.close()
    return [dict(r) for r in rows]


def get_employee(employee_code: str):
    conn = get_connection(); row = conn.execute("SELECT * FROM employees WHERE employee_code=?", (employee_code,)).fetchone(); conn.close()
    return dict(row) if row else None


def employee_count():
    conn = get_connection(); row = conn.execute("SELECT COUNT(*) c FROM employees").fetchone(); conn.close(); return row["c"] if row else 0


def next_employee_code():
    conn = get_connection(); rows = conn.execute("SELECT employee_code FROM employees").fetchall(); conn.close()
    nums = []
    for r in rows:
        try: nums.append(int(str(r["employee_code"]).split("-")[-1]))
        except (ValueError, TypeError): pass
    return f"TT-EMP-{(max(nums)+1 if nums else 1):04d}"


def get_all_employee_names():
    conn = get_connection(); rows = conn.execute("SELECT employee_code,employee_name FROM employees ORDER BY employee_name").fetchall(); conn.close()
    return [dict(r) for r in rows]


def get_statutory_summary():
    conn = get_connection(); row = conn.execute("""SELECT
      COALESCE(SUM(employer_pf),0) total_employer_epf,
      COALESCE(SUM(employer_eps),0) total_employer_eps,
      COALESCE(SUM(employer_edli),0) total_employer_edli,
      COALESCE(SUM(employer_admin_charges),0) total_admin_charges,
      COALESCE(SUM(employer_pf_total),0) total_employer_pf,
      COALESCE(SUM(employer_esic),0) total_employer_esic,
      COALESCE(SUM(employee_esic),0) total_employee_esic,
      COALESCE(SUM(pf),0) total_employee_pf, COUNT(*) employee_count
      FROM employees WHERE status='Active'""").fetchone(); conn.close(); return dict(row)


def get_leave_balance(employee_code: str):
    conn = get_connection(); rows = conn.execute("SELECT leave_type,SUM(days) used FROM leave_requests WHERE employee_code=? AND status='Approved' GROUP BY leave_type", (employee_code,)).fetchall(); conn.close()
    used = {r["leave_type"]: float(r["used"] or 0) for r in rows}
    return {"casual_total":12.0,"casual_used":used.get("Casual",0),"sick_total":7.0,"sick_used":used.get("Sick",0),"earned_total":15.0,"earned_used":used.get("Earned",0)}


def apply_leave(employee_code, leave_type, from_date, to_date, days, reason):
    conn = get_connection(); conn.execute("INSERT INTO leave_requests(employee_code,leave_type,from_date,to_date,days,reason) VALUES(?,?,?,?,?,?)", (employee_code,leave_type,str(from_date),str(to_date),float(days),(reason or "").strip())); conn.commit(); conn.close()


def get_leave_requests(employee_code=None):
    conn = get_connection()
    q, args = ("SELECT * FROM leave_requests WHERE employee_code=? ORDER BY applied_on DESC", (employee_code,)) if employee_code else ("SELECT * FROM leave_requests ORDER BY applied_on DESC", ())
    rows = conn.execute(q,args).fetchall(); conn.close(); return [dict(r) for r in rows]


def decide_leave(request_id: int, status: str):
    if status not in {"Approved","Rejected","Pending"}: return False
    conn = get_connection(); cur = conn.execute("UPDATE leave_requests SET status=? WHERE id=?", (status,request_id)); conn.commit(); ok=cur.rowcount==1; conn.close(); return ok


def add_announcement(title, message):
    conn=get_connection(); conn.execute("INSERT INTO announcements(title,message) VALUES(?,?)",((title or "").strip(),(message or "").strip())); conn.commit(); conn.close()


def get_announcements(limit=10):
    conn=get_connection(); rows=conn.execute("SELECT * FROM announcements ORDER BY created_at DESC LIMIT ?",(int(limit),)).fetchall(); conn.close(); return [dict(r) for r in rows]
