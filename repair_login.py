"""TEC TANIVA HRMS login repair utility.

Run from the project directory:
  python repair_login.py admin
  python repair_login.py employee TT-EMP-0001
  python repair_login.py employee TT-EMP-0001 --password Welcome@123

This utility intentionally changes passwords only when you explicitly run it.
"""
from __future__ import annotations
import argparse
import getpass
from database import init_db, get_employee, get_user_by_employee_code, change_password, create_user, username_exists


def main():
    parser = argparse.ArgumentParser(description="Repair TEC TANIVA HRMS portal login")
    parser.add_argument("kind", choices=["admin", "employee"])
    parser.add_argument("employee_code", nargs="?")
    parser.add_argument("--password", dest="password")
    args = parser.parse_args()
    init_db()

    password = args.password or getpass.getpass("New password: ")
    if len(password.strip()) < 8:
        raise SystemExit("Password must contain at least 8 characters.")
    password = password.strip()

    if args.kind == "admin":
        from database import get_connection
        conn = get_connection()
        row = conn.execute("SELECT username FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
        conn.close()
        username = row["username"] if row else "admin"
        if change_password(username, password):
            print(f"SUCCESS: Admin password reset. Username: {username}")
        else:
            raise SystemExit("ERROR: No admin account exists. Run init_db again or inspect the database.")
        return

    code = (args.employee_code or "").strip().upper()
    if not code:
        raise SystemExit("Employee code is required, e.g. TT-EMP-0001")
    emp = get_employee(code)
    if not emp:
        raise SystemExit(f"ERROR: Employee {code} was not found in the database.")
    user = get_user_by_employee_code(code)
    if user:
        username = user["username"]
        if not change_password(username, password):
            raise SystemExit("ERROR: Could not update the employee password.")
    else:
        username = code.casefold()
        if username_exists(username):
            raise SystemExit(f"ERROR: Username {username} is already used by another account.")
        if not create_user(username, password, "employee", code, emp.get("employee_name")):
            raise SystemExit("ERROR: Could not create the employee portal account.")
    print(f"SUCCESS: Employee portal repaired. Username: {username}  Employee: {code}")


if __name__ == "__main__":
    main()
