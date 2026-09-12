# TEC TANIVA HRMS — Production Authentication Fix

## Default admin
- Username: `admin`
- Password: `admin123` **only if the database had no admin account before first startup**.

The application does not overwrite existing admin passwords on startup.

## Start Admin
```powershell
python -m pip install -r requirements.txt
streamlit run admin.py
```

## Start Employee Portal
```powershell
streamlit run employee_count.py
```

## Repair an admin password
If `admin / admin123` fails because your existing database has a different/old admin password:
```powershell
python repair_login.py admin
```
Enter a new password with at least 8 characters.

## Repair an employee login
For the employee shown in the screenshot:
```powershell
python repair_login.py employee TT-EMP-0001 --password Welcome@123
```

This will update the existing linked employee account. If the account is missing, it will create exactly one account using `tt-emp-0001`.

## Why this version fixes the problem
1. Username matching is case-insensitive and trims accidental surrounding whitespace.
2. Employee codes are normalized to uppercase when looking up linked accounts.
3. The Admin reset action really writes the new password hash to the same SQLite database used by the portal.
4. If an employee record exists but its portal login was deleted, Admin reset recreates the one-to-one login.
5. Legacy SHA-256 password hashes continue to work and are upgraded after a successful login.
6. New passwords use salted PBKDF2-SHA256.
7. No URL `auth=` login token is used. Authentication is stored in the Streamlit session.

## Important deployment rule
Keep the `database/hr_system.db` file on persistent storage. Do not deploy SQLite on an ephemeral filesystem if you need data to survive restarts/redeployments. For multiple production instances, migrate the database to PostgreSQL.

## If the browser keeps an old session
Close the old portal tab completely and open the current Streamlit URL again. The new version does not rely on URL authentication tokens.
