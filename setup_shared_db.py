import argparse, os, shutil
from database import SHARED_DB_PATH, init_db, get_database_info

p = argparse.ArgumentParser(description='Point TEC TANIVA HRMS to one shared database')
p.add_argument('--source', help='Existing hr_system.db to copy into the shared HRMS database')
p.add_argument('--force', action='store_true')
a = p.parse_args()

if a.source:
    source = os.path.abspath(a.source)
    if not os.path.isfile(source):
        raise SystemExit(f'Source database not found: {source}')
    if os.path.exists(SHARED_DB_PATH) and not a.force:
        raise SystemExit(f'Shared DB already exists: {SHARED_DB_PATH}\nUse --force only after making a backup.')
    os.makedirs(os.path.dirname(SHARED_DB_PATH), exist_ok=True)
    shutil.copy2(source, SHARED_DB_PATH)
    print(f'Copied database to: {SHARED_DB_PATH}')

init_db()
print(get_database_info())
