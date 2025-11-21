# init_db.py
# Run this once to create app.db from schema.sql
# Usage: python init_db.py

import sqlite3
import pathlib
import sys

DB_FILE = "app.db"
SCHEMA_FILE = "schema.sql"

def init_db(db_file=DB_FILE, schema_file=SCHEMA_FILE):
    if not pathlib.Path(schema_file).exists():
        print(f"Schema file {schema_file} not found.")
        sys.exit(1)
    with open(schema_file, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn = sqlite3.connect(db_file)
    try:
        cursor = conn.cursor()
        cursor.executescript(schema_sql)
        conn.commit()
        print(f"Database initialized at {db_file}")
    except Exception as e:
        print("Error initializing DB:", e)
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()