#!/usr/bin/env python3
"""
fix_duplicate_slugs.py
Añade sufijos _1, _2 ... a slugs duplicados en slugs.csv para hacerlos únicos.
Usage:
  python fix_duplicate_slugs.py --in slugs.csv --out slugs_fixed.csv
  python fix_duplicate_slugs.py --in slugs.csv --out slugs.csv --overwrite
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", required=True, help="Input CSV (slug,name)")
    p.add_argument("--out", dest="out", default="slugs_fixed.csv", help="Output CSV")
    p.add_argument("--overwrite", action="store_true", help="Overwrite input file with fixed output")
    args = p.parse_args()

    inp = Path(args.inp)
    if not inp.exists():
        raise SystemExit(f"Input file no encontrado: {inp}")

    rows = []
    counts = defaultdict(int)
    with inp.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
            counts[r["slug"]] += 1

    seen = {}
    out_rows = []
    for r in rows:
        slug = r["slug"]
        name = r["name"]
        if slug not in seen:
            seen[slug] = 1
            out_rows.append({"slug": slug, "name": name})
        else:
            seen[slug] += 1
            new_slug = f"{slug}_{seen[slug]-1}"
            out_rows.append({"slug": new_slug, "name": name})

    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["slug","name"])
        writer.writeheader()
        writer.writerows(out_rows)

    if args.overwrite:
        inp.unlink()
        out_path.rename(inp)

    print(f"Salida escrita: {out_path} ({len(out_rows)} entradas)")

if __name__ == "__main__":
    main()