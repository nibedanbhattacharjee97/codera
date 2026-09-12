# TEC TANIVA HRMS — FINAL Production Authentication Fix

## Root cause addressed
Admin and Employee now use one project-local SQLite database: `database/hr_system.db`.
On first run, if the database has no employees, the bundled `data.xlsx` is imported automatically and a portal login is created for each imported employee.

## Default credentials
Admin: `admin` / `admin123`
Imported employees: username = employee code, temporary password = `Welcome@123`

## IMPORTANT about TT-EMP-0001
The `data.xlsx` supplied with the project contains employee codes `TT-EMP-0003` through `TT-EMP-0012`; it does **not** contain `TT-EMP-0001`. Therefore this package cannot legitimately create a profile for TT-EMP-0001 from that spreadsheet. If your real database contains TT-EMP-0001, copy that database to this project's `database/hr_system.db` before first launch, or set `HRMS_DB_PATH` to its path.

## Run
```powershell
pip install -r requirements.txt
streamlit run admin.py
```
Then: `admin / admin123`.

Employee:
```powershell
streamlit run employee_count.py
```
For the supplied spreadsheet, test `TT-EMP-0003 / Welcome@123`.

## Repair
```powershell
python repair_login.py employee TT-EMP-0001 --password Welcome@123
python repair_login.py admin --password NewStrongAdminPassword123!
python diagnose_login.py --username TT-EMP-0001 --password Welcome@123
```

## Existing database
Back up your current `database/hr_system.db` and place the copy into the new project's `database` folder before first launch. If you need to import a database after startup, use `python setup_shared_db.py --source "C:\path\to\hr_system.db" --force`. The code will preserve existing employee passwords.
