import argparse
from database import init_db, get_connection, get_database_info, authenticate_user, reset_employee_password

p=argparse.ArgumentParser(description='TEC TANIVA HRMS login diagnostic')
p.add_argument('--username')
p.add_argument('--password')
p.add_argument('--employee')
p.add_argument('--reset-password')
a=p.parse_args()
init_db()
print('\nDATABASE')
for k,v in get_database_info().items(): print(f'{k}: {v}')
conn=get_connection()
print('\nUSERS')
for r in conn.execute('SELECT id, username, role, employee_code, full_name FROM users ORDER BY id'):
    print(dict(r))
print('\nEMPLOYEES')
for r in conn.execute('SELECT employee_code, employee_name, status FROM employees ORDER BY employee_code'):
    print(dict(r))
conn.close()
if a.username is not None and a.password is not None:
    u=authenticate_user(a.username,a.password)
    print('\nAUTH TEST:', 'SUCCESS' if u else 'FAILED')
    if u: print(dict(u))
if a.employee and a.reset_password:
    u=reset_employee_password(a.employee,a.reset_password)
    print('\nEMPLOYEE RESET:', u or 'FAILED - employee missing or username conflict')
