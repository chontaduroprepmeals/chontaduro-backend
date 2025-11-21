#!/usr/bin/env python3
"""
Import allowed_zips_noheader.csv into app.db (SQLite).
Usage: .venv/bin/python import_allowed_zips.py
"""
import csv
import sqlite3
from pathlib import Path
DB = Path("app.db")
CSV = Path("allowed_zips_noheader.csv")

print("DEBUG: db:", DB.resolve())
print("DEBUG: csv:", CSV.resolve())

if not DB.exists():
    print("Warning: app.db not found in current directory:", DB.resolve())

if not CSV.exists():
    raise SystemExit(f"CSV not found: {CSV.resolve()}")

conn = sqlite3.connect(str(DB))
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS delivery_allowed_zips (
  zip TEXT PRIMARY KEY,
  distance_miles REAL,
  place_name TEXT,
  lat REAL,
  lon REAL
);
""")

rows = []
with CSV.open(newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    for r in reader:
        if len(r) < 5:
            continue
        zipc = r[0].strip()
        try:
            dist = float(r[1])
        except:
            dist = 0.0
        place = r[2].strip()
        try:
            lat = float(r[3]); lon = float(r[4])
        except:
            lat = lon = 0.0
        rows.append((zipc, dist, place, lat, lon))

if rows:
    c.executemany("INSERT OR REPLACE INTO delivery_allowed_zips(zip, distance_miles, place_name, lat, lon) VALUES (?, ?, ?, ?, ?)", rows)
    c.execute("CREATE INDEX IF NOT EXISTS idx_delivery_allowed_zips_distance ON delivery_allowed_zips(distance_miles)")
    conn.commit()
    print("Imported", len(rows), "rows into", DB)
else:
    print("No rows to import (CSV empty or malformed)")

conn.close()