# TEC TANIVA HRMS — Production Login Fix

## Run the employee portal
```bash
python -m pip install -r requirements.txt
streamlit run employee_count.py
```

## Run the admin portal
```bash
streamlit run admin.py
```

### Default admin
The existing legacy admin password remains compatible: `admin / admin123`.
Change it after first deployment. New passwords are stored with salted PBKDF2-SHA256; old SHA-256 passwords are automatically upgraded after a successful login.

### Employee login
The employee username is the username shown by **Admin → Portal Access**. It is normalized to lowercase and surrounding username whitespace is ignored.

If Admin shows **"This employee already has a portal login"**, do **not** create another account. Use **Reset Password**, then sign in with the displayed username and the new password.

### Important production change
The employee portal no longer uses a URL `auth=` token. Authentication is stored in the Streamlit session, which avoids stale/shared login tokens and role-mismatch problems.

### Import the supplied Excel data (optional)
Only do this if your SQLite database does not already contain the employee records:

Windows PowerShell:
```powershell
$env:INITIAL_EMPLOYEE_PASSWORD="Temporary@123"
python seed_from_excel.py
```

Then change the employee passwords from Admin → Portal Access.

## Troubleshooting
1. Restart Streamlit after replacing the files.
2. Clear the browser tab/session if an old login page remains.
3. In Admin → Portal Access, select the exact employee and reset the password.
4. Make sure the employee account is linked to the same employee code as the employee master record.
5. Do not delete `database/hr_system.db` unless you intentionally want to start over.
6. For multi-user production hosting, use a persistent SQLite volume or migrate the data layer to PostgreSQL; ephemeral hosting can otherwise lose SQLite changes on redeploy.
