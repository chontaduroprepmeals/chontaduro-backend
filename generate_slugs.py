#!/usr/bin/env python3
"""
generate_slugs.py
Genera un archivo CSV (slug,name) a partir de meals.json usando una función slugify
Usage:
  python generate_slugs.py --meals meals.json --output slugs.csv
"""
import argparse
import json
import re
from pathlib import Path
import csv

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[’'\"`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_{2,}", "_", s)
    s = s.strip("_")
    return s or "item"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--meals", default="meals.json", help="Ruta a meals.json")
    p.add_argument("--output", default="slugs.csv", help="CSV output (slug,name)")
    args = p.parse_args()

    path = Path(args.meals)
    if not path.exists():
        raise SystemExit(f"meals.json no encontrado: {path}")

    meals = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for m in meals:
        name = m.get("name") or m.get("title") or ""
        slug = slugify(name)
        rows.append({"slug": slug, "name": name})

    out = Path(args.output)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["slug","name"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"CSV escrito: {out} ({len(rows)} entradas)")

if __name__ == "__main__":
    main()