#!/usr/bin/env python3
"""
import_meals.py
Lee meals.json y vuelca los registros a la tabla `meals` en app.db.

Uso:
  ./.venv/bin/python import_meals.py

Notas:
- Trata de mantener meals.json en el mismo formato que ya tienes.
- Mapea keys (name,type,ingredients,calories,protein_g,cost_estimate,price,image_url,tags).
- Si no hay algún campo, se inserta NULL.
"""
import json
import sqlite3
import pathlib
import sys

DB_FILE = "app.db"
MEALS_FILE = "meals.json"

def normalize_meal(m):
    # Ajusta claves comunes y tipos
    out = {}
    out["name"] = m.get("name") or m.get("nombre") or ""
    out["type"] = m.get("type") or m.get("tipo") or "Main Meal"
    # ingredients -> store as JSON string
    ings = m.get("ingredients", m.get("ingredientes", []))
    if isinstance(ings, str):
        ings = [i.strip() for i in ings.split(",") if i.strip()]
    out["ingredients"] = json.dumps(ings, ensure_ascii=False)
    # numeric fields
    try:
        out["calories"] = int(m.get("calories") or m.get("calorias") or 0)
    except Exception:
        out["calories"] = None
    try:
        out["protein_g"] = float(m.get("protein_g") or m.get("proteing") or m.get("protein") or 0)
    except Exception:
        out["protein_g"] = None
    try:
        out["cost_estimate"] = float(m.get("cost_estimate") or m.get("cost") or m.get("precio") or 0)
    except Exception:
        out["cost_estimate"] = None
    try:
        out["price"] = float(m.get("price") or 0)
    except Exception:
        out["price"] = None
    out["image_url"] = m.get("image_url") or m.get("imagen") or None
    tags = m.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    out["tags"] = json.dumps(tags, ensure_ascii=False)
    return out

def import_meals(db_file=DB_FILE, meals_file=MEALS_FILE):
    p = pathlib.Path(meals_file)
    if not p.exists():
        print(f"meals.json not found at {meals_file}")
        sys.exit(1)
    with open(meals_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print("meals.json should be a list of meals")
        sys.exit(1)

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    inserted = 0
    for m in data:
        nm = normalize_meal(m)
        try:
            cur.execute("""python import_meals.py
                INSERT OR IGNORE INTO meals (name, type, ingredients, calories, protein_g, cost_estimate, price, image_url, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nm["name"], nm["type"], nm["ingredients"], nm["calories"],
                nm["protein_g"], nm["cost_estimate"], nm["price"], nm["image_url"], nm["tags"]
            ))
            inserted += cur.rowcount
        except Exception as e:
            print("ERROR inserting", nm.get("name"), e)
    conn.commit()
    conn.close()
    print(f"Import finished. Attempted {len(data)} meals. Inserted/ignored: {inserted}")

if __name__ == "__main__":
    import_meals()