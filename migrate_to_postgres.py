"""
migrate_to_postgres.py
100% Standalone migration script.
Direct URL configuration (No secrets.toml needed).
"""

import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_values

# ==============================================================================
# PASTE YOUR POSTGRESQL CONNECTION STRING DIRECTLY HERE:
# Example: "postgresql://username:password@ep-cool-db.us-east-1.aws.neon.tech/neondb?sslmode=require"
# ==============================================================================
POSTGRES_URL = "postgresql://neondb_owner:npg_v4xFVDUTu1ny@ep-plain-fire-b38fcppk-pooler.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

BASE_DIR = os.path.dirname(__file__)
SQLITE_DB_PATH = os.path.join(BASE_DIR, "database", "hr_system.db")

def create_tables(pg_cur):
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'employee')),
            employee_code TEXT,
            full_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            employee_code TEXT UNIQUE NOT NULL,
            employee_name TEXT NOT NULL,
            dob TEXT,
            highest_qualification TEXT,
            date_of_joining TEXT,
            designation TEXT,
            reporting_boss TEXT,
            reporting_boss_code TEXT,
            mobile_number TEXT,
            uan_number TEXT,
            esic_number TEXT,
            employee_type TEXT CHECK(employee_type IN ('Probation', 'Permanent')),
            emergency_contact_number TEXT,
            email TEXT,
            place TEXT,
            bank_name TEXT,
            ifsc_code TEXT,
            blood_group TEXT,
            pic_path TEXT,
            id_card_path TEXT,
            certificate_path TEXT,
            cv_path TEXT,
            extra_doc1_path TEXT,
            extra_doc2_path TEXT,
            extra_doc3_path TEXT,
            extra_doc4_path TEXT,
            basic_pay DOUBLE PRECISION DEFAULT 0,
            da DOUBLE PRECISION DEFAULT 0,
            hra DOUBLE PRECISION DEFAULT 0,
            phonebill_pay DOUBLE PRECISION DEFAULT 0,
            others DOUBLE PRECISION DEFAULT 0,
            pf_basis TEXT CHECK(pf_basis IN ('capped', 'actual')) DEFAULT 'capped',
            pf_wage DOUBLE PRECISION DEFAULT 0,
            pf DOUBLE PRECISION DEFAULT 0,
            employer_pf DOUBLE PRECISION DEFAULT 0,
            employer_eps DOUBLE PRECISION DEFAULT 0,
            employer_edli DOUBLE PRECISION DEFAULT 0,
            employer_admin_charges DOUBLE PRECISION DEFAULT 0,
            employer_pf_total DOUBLE PRECISION DEFAULT 0,
            is_pwd INTEGER DEFAULT 0,
            esic_if_applicable TEXT CHECK(esic_if_applicable IN ('Yes', 'No')) DEFAULT 'No',
            esic_wage_ceiling_used DOUBLE PRECISION DEFAULT 0,
            esic_eligible_by_wage INTEGER DEFAULT 0,
            employer_esic DOUBLE PRECISION DEFAULT 0,
            employee_esic DOUBLE PRECISION DEFAULT 0,
            food_reimbursement TEXT CHECK(food_reimbursement IN ('Yes', 'No')) DEFAULT 'No',
            ctc DOUBLE PRECISION DEFAULT 0,
            leave_balance DOUBLE PRECISION DEFAULT 12,
            status TEXT DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS leave_requests (
            id SERIAL PRIMARY KEY,
            employee_code TEXT NOT NULL,
            leave_type TEXT,
            from_date TEXT,
            to_date TEXT,
            days DOUBLE PRECISION,
            reason TEXT,
            status TEXT DEFAULT 'Pending',
            boss_employee_code TEXT,
            decided_by TEXT,
            decided_at TIMESTAMP,
            applied_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_code) REFERENCES employees(employee_code) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS announcements (
            id SERIAL PRIMARY KEY,
            title TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS leave_balances (
            id SERIAL PRIMARY KEY,
            employee_code TEXT NOT NULL,
            leave_type TEXT NOT NULL,
            balance DOUBLE PRECISION DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_code, leave_type)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            recipient_code TEXT NOT NULL,
            title TEXT,
            message TEXT,
            related_type TEXT,
            related_id INTEGER,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS payroll_records (
            id SERIAL PRIMARY KEY,
            employee_code TEXT NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            basic_pay DOUBLE PRECISION DEFAULT 0,
            da DOUBLE PRECISION DEFAULT 0,
            hra DOUBLE PRECISION DEFAULT 0,
            phonebill_pay DOUBLE PRECISION DEFAULT 0,
            others DOUBLE PRECISION DEFAULT 0,
            gross DOUBLE PRECISION DEFAULT 0,
            employee_pf DOUBLE PRECISION DEFAULT 0,
            employee_esic DOUBLE PRECISION DEFAULT 0,
            employer_pf_total DOUBLE PRECISION DEFAULT 0,
            employer_esic DOUBLE PRECISION DEFAULT 0,
            ctc DOUBLE PRECISION DEFAULT 0,
            net_pay DOUBLE PRECISION DEFAULT 0,
            lop_days DOUBLE PRECISION DEFAULT 0,
            lop_amount DOUBLE PRECISION DEFAULT 0,
            extra_days DOUBLE PRECISION DEFAULT 0,
            extra_amount DOUBLE PRECISION DEFAULT 0,
            per_day_rate DOUBLE PRECISION DEFAULT 0,
            present_days DOUBLE PRECISION DEFAULT 0,
            source TEXT DEFAULT 'manual',
            generated_by TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_code, month, year)
        );
        CREATE TABLE IF NOT EXISTS lop_extra_records (
            id SERIAL PRIMARY KEY,
            employee_code TEXT NOT NULL,
            record_type TEXT NOT NULL CHECK(record_type IN ('LOP', 'EXTRA')),
            record_date TEXT NOT NULL,
            day_count DOUBLE PRECISION NOT NULL DEFAULT 1,
            reason TEXT,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_code) REFERENCES employees(employee_code) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS attendance_records (
            id SERIAL PRIMARY KEY,
            employee_code TEXT NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            day INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_code, month, year, day)
        );
    """)

TABLES = [
    "users",
    "employees",
    "leave_balances",
    "leave_requests",
    "payroll_records",
    "lop_extra_records",
    "attendance_records",
    "announcements",
    "notifications",
]

def run_migration():
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"[-] SQLite file not found at {SQLITE_DB_PATH}")
        return

    if POSTGRES_URL == "YOUR_POSTGRESQL_CONNECTION_URL_HERE" or not POSTGRES_URL:
        print("[-] Error: Please replace YOUR_POSTGRESQL_CONNECTION_URL_HERE with your real Postgres connection string at the top of the file.")
        return

    print("[*] Connecting to SQLite and PostgreSQL...")
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(POSTGRES_URL)

    try:
        with pg_conn.cursor() as pg_cur:
            print("[*] Ensuring PostgreSQL tables exist...")
            create_tables(pg_cur)
            pg_conn.commit()

            for table in TABLES:
                print(f"[*] Processing table: {table}...")

                cur = sqlite_conn.execute(f"PRAGMA table_info({table});")
                cols = [row[1] for row in cur.fetchall()]

                rows = sqlite_conn.execute(f"SELECT * FROM {table};").fetchall()
                if not rows:
                    print(f"    - No rows found in {table}. Skipped.")
                    continue

                col_names = ", ".join([f'"{c}"' for c in cols])
                data_tuples = [tuple(r[c] for c in cols) for r in rows]

                insert_sql = f"""
                    INSERT INTO {table} ({col_names})
                    VALUES %s
                    ON CONFLICT DO NOTHING;
                """
                execute_values(pg_cur, insert_sql, data_tuples)
                print(f"    - Migrated {len(rows)} row(s) into {table}.")

                if "id" in cols:
                    pg_cur.execute(f"""
                        SELECT setval(
                            pg_get_serial_sequence('{table}', 'id'),
                            COALESCE((SELECT MAX(id) FROM {table}), 1)
                        );
                    """)

            pg_conn.commit()
            print("\n[+] Migration completed successfully! All data transferred to PostgreSQL.")

    except Exception as e:
        pg_conn.rollback()
        print(f"\n[-] Migration failed with error: {e}")
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    run_migration()