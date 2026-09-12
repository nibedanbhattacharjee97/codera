# TEC TANIVA HRMS - Authentication Fixed

## Important fix
Admin and Employee now use one shared SQLite database at:
`%USERPROFILE%\.tec_taniva_hrms\hr_system.db` on Windows.

This prevents Admin and Employee from using different copies of `database/hr_system.db`. You can override it with the `HRMS_DB_PATH` environment variable.

## Start
1. `pip install -r requirements.txt`
2. Double-click `run_admin.bat` for Admin.
3. Double-click `run_employee.bat` for Employee.

## Default admin
Username: `admin`
Password: `admin123`

Change it immediately in production.

## Repair employee login
After Admin selects an employee in Portal Access and clicks Reset Password, the reset now creates the employee portal account if it is missing.

Command line example:
`python repair_login.py employee TT-EMP-0001 --password Welcome@123`

## Existing database
On first run, if the shared database does not exist and the project contains `database/hr_system.db`, that local database is copied into the shared location.

## Security
New passwords use PBKDF2-HMAC-SHA256 with a random salt. Existing legacy SHA-256 password hashes are accepted once and upgraded after successful login. No credentials are accepted from URL query parameters.
