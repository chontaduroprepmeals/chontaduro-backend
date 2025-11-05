import json, sys

with open("meals.json","r",encoding="utf-8") as f: meals = json.load(f)
with open("menus_weekly.json","r",encoding="utf-8") as f: templates = json.load(f)

meal_names = {m.get("name","").strip().lower() for m in meals}
missing = {}
for tpl in templates:
    missing_in_tpl = []
    for pool in ("mains","breakfasts"):
        for name in tpl.get("pool", {}).get(pool, []):
            if name.strip().lower() not in meal_names:
                missing_in_tpl.append(name)
    if missing_in_tpl:
        missing[tpl.get("id")] = missing_in_tpl

print("Missing entries:", missing)