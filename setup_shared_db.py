import argparse, os, shutil
from database import DB_PATH, init_db, get_database_info

p=argparse.ArgumentParser(description="Import an existing TEC TANIVA HRMS database")
p.add_argument("--source", required=True, help="Existing hr_system.db")
p.add_argument("--force", action="store_true")
a=p.parse_args()
source=os.path.abspath(a.source)
if not os.path.isfile(source): raise SystemExit(f"Source database not found: {source}")
if os.path.abspath(source)==os.path.abspath(DB_PATH): raise SystemExit("Source is already the active database.")
if os.path.exists(DB_PATH) and not a.force: raise SystemExit(f"Active DB already exists: {DB_PATH}. Back it up and use --force to replace it.")
os.makedirs(os.path.dirname(DB_PATH),exist_ok=True)
shutil.copy2(source,DB_PATH)
init_db()
print(get_database_info())
