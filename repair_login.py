import argparse
from database import init_db, reset_employee_password, change_password, get_database_info

def main():
    p = argparse.ArgumentParser(description="TEC TANIVA HRMS login repair utility")
    sub = p.add_subparsers(dest="command", required=True)
    pa = sub.add_parser("admin")
    pa.add_argument("--password", required=True)
    pe = sub.add_parser("employee")
    pe.add_argument("employee_code")
    pe.add_argument("--password", required=True)
    args = p.parse_args()
    init_db()
    if args.command == "admin":
        change_password("admin", args.password)
        print("Admin password reset for username: admin")
    else:
        username = reset_employee_password(args.employee_code, args.password)
        if not username:
            raise SystemExit("Employee not found or username conflict.")
        print(f"Employee login repaired: {username}")
    print(get_database_info())

if __name__ == "__main__":
    main()
