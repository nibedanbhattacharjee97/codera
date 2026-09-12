import argparse
from database import init_db, reset_employee_password, change_password, get_database_info, authenticate_user

def main():
    p=argparse.ArgumentParser(description="TEC TANIVA HRMS login repair")
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("admin"); a.add_argument("--password",required=True)
    e=sub.add_parser("employee"); e.add_argument("employee_code"); e.add_argument("--password",required=True)
    args=p.parse_args(); init_db()
    if args.command=="admin":
        change_password("admin",args.password); print("Admin password reset: admin")
        print("Test:","SUCCESS" if authenticate_user("admin",args.password) else "FAILED")
    else:
        u=reset_employee_password(args.employee_code,args.password)
        if not u: raise SystemExit("Employee not found or username conflict. Check the employee code with diagnose_login.py.")
        print(f"Employee login repaired: {u}")
        print("Test:","SUCCESS" if authenticate_user(u,args.password) else "FAILED")
    print(get_database_info())
if __name__=="__main__": main()
