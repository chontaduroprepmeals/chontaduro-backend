"""
Recalculate meal macros in meals.json using USDA FoodData Central.

Standard portions are fixed by ingredient class and ingredient name.
Breakfast target range: 350-500 kcal.
Main meal target range: 400-600 kcal.
Protein hard cap: 40g per meal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from usda_nutrition import fetch_nutrition_for_ingredient


ROOT = Path(__file__).resolve().parent
MEALS_PATH = ROOT / "meals.json"


ANIMAL_PROTEIN_MARKERS = {
    "chicken",
    "turkey",
    "beef",
    "pork",
    "tuna",
    "sardine",
    "egg",
    "tilapia",
    "salmon",
    "shrimp",
    "fish",
}


def _rule(pattern: str, portion_g: float, usda_query: str) -> Dict[str, object]:
    return {"pattern": pattern, "portion_g": portion_g, "query": usda_query}


# Ordered matching: first match wins.
INGREDIENT_RULES: List[Dict[str, object]] = [
    # Condiments and fixed extras
    _rule("olive oil", 10.0, "oil, olive, salad or cooking"),
    _rule("butter", 8.0, "butter, salted"),
    _rule("soy sauce", 15.0, "soy sauce made from soy and wheat"),
    _rule("garlic", 5.0, "garlic, raw"),
    _rule("spices", 2.0, "spices, mixed, allspice"),
    _rule("spice", 2.0, "spices, mixed, allspice"),
    _rule("salt", 2.0, "salt, table"),
    _rule("lemon", 15.0, "lemon, raw"),
    _rule("lime", 15.0, "limes, raw"),
    _rule("honey", 10.0, "honey"),

    # Fruit fixed portions
    _rule("banana", 100.0, "bananas, raw"),
    _rule("apple", 120.0, "apples, raw, with skin"),
    _rule("papaya", 100.0, "papayas, raw"),

    # Dairy / other protein
    _rule("greek yogurt", 150.0, "yogurt, greek, plain, nonfat"),
    _rule("cottage cheese", 150.0, "cottage cheese, lowfat, 2% milkfat"),
    _rule("fresh cheese", 30.0, "cheese, queso fresco"),
    _rule("mozzarella", 30.0, "cheese, mozzarella, part skim milk"),
    _rule("regular milk", 120.0, "milk, reduced fat, fluid, 2% milkfat"),
    _rule("protein powder", 30.0, "protein powder, whey based"),

    # Animal proteins
    _rule("whole chicken", 200.0, "chicken, broilers or fryers, leg, meat and skin, raw"),
    _rule("chicken breast", 170.0, "chicken breast, meat only, raw"),
    _rule("ground beef", 170.0, "ground beef 90 lean raw"),
    _rule("lean ground beef", 170.0, "ground beef 90 lean raw"),
    _rule("ground turkey", 170.0, "ground turkey, 93% lean, raw"),
    _rule("ground chicken", 170.0, "ground chicken, raw"),
    _rule("chicken meatballs", 170.0, "ground chicken, raw"),
    _rule("turkey meatballs", 170.0, "ground turkey, 93% lean, raw"),
    _rule("canned tuna", 170.0, "tuna, canned in water, drained solids"),
    _rule("canned sardines", 170.0, "sardines, canned in tomato sauce, drained solids"),
    _rule("pork", 170.0, "pork, fresh, loin, tenderloin, separable lean only, raw"),
    _rule("tilapia", 170.0, "fish, tilapia, raw"),
    _rule("egg whites", 120.0, "egg white, raw, fresh"),
    _rule("scrambled eggs", 120.0, "eggs, whole, raw, fresh"),
    _rule("eggs", 120.0, "eggs, whole, raw, fresh"),
    _rule("egg", 120.0, "eggs, whole, raw, fresh"),

    # Carb sources
    _rule("brown rice", 150.0, "rice, brown, cooked"),
    _rule("white rice", 150.0, "rice, white, cooked"),
    _rule("rice noodles", 120.0, "rice noodles, cooked"),
    _rule("whole wheat pasta", 120.0, "pasta, whole-wheat, cooked"),
    _rule("white pasta", 120.0, "pasta, cooked, unenriched, without added salt"),
    _rule("yellow potatoes", 120.0, "potatoes, boiled, cooked without skin, flesh, without salt"),
    _rule("white potatoes", 120.0, "potatoes, boiled, cooked without skin, flesh, without salt"),
    _rule("white potato", 120.0, "potatoes, boiled, cooked without skin, flesh, without salt"),
    _rule("sweet potato", 120.0, "sweet potato, cooked, baked in skin, flesh, without salt"),
    _rule("corn tortillas", 60.0, "tortilla, corn"),
    _rule("flour tortilla", 45.0, "tortilla, flour"),
    _rule("arepa", 80.0, "cornmeal, cooked"),
    _rule("whole wheat bread", 60.0, "bread, whole-wheat, commercially prepared"),
    _rule("oats", 80.0, "oats"),
    _rule("ripe plantain", 80.0, "plantains, raw"),
    _rule("corn", 80.0, "corn, sweet, yellow, cooked, boiled, drained, without salt"),

    # Legumes treated as carb sources in cooked portions
    _rule("chickpeas", 120.0, "chickpeas (garbanzo beans, bengal gram), mature seeds, cooked, boiled, without salt"),
    _rule("black beans", 120.0, "beans, black, mature seeds, cooked, boiled, without salt"),
    _rule("red beans", 120.0, "beans, kidney, red, mature seeds, cooked, boiled, without salt"),
    _rule("lentils", 120.0, "lentils, mature seeds, cooked, boiled, without salt"),

    # Vegetables 100g
    _rule("broccoli", 100.0, "broccoli, raw"),
    _rule("cauliflower", 100.0, "cauliflower, raw"),
    _rule("cabbage", 100.0, "cabbage, raw"),
    _rule("zucchini", 100.0, "zucchini, raw"),
    _rule("spinach", 100.0, "spinach, raw"),
    _rule("green beans", 100.0, "beans, snap, green, raw"),
    _rule("mixed frozen vegetables", 100.0, "vegetables mixed, frozen, cooked, boiled, drained, without salt"),
    _rule("mixed vegetables", 100.0, "vegetables mixed, frozen, cooked, boiled, drained, without salt"),

    # Vegetables 60g
    _rule("tomato", 60.0, "tomatoes, red, ripe, raw, year round average"),
    _rule("cucumber", 60.0, "cucumber, with peel, raw"),
    _rule("romaine lettuce", 60.0, "lettuce, cos or romaine, raw"),
    _rule("lettuce", 60.0, "lettuce, green leaf, raw"),
    _rule("bell pepper", 60.0, "peppers, sweet, green, raw"),
    _rule("red bell pepper", 60.0, "peppers, sweet, red, raw"),
    _rule("onion", 60.0, "onions, raw"),
    _rule("celery", 60.0, "celery, raw"),
    _rule("carrots", 60.0, "carrots, raw"),
    _rule("carrot", 60.0, "carrots, raw"),
]


def get_portion_and_query(ingredient: str) -> Tuple[float, str]:
    text = (ingredient or "").strip().lower()
    for rule in INGREDIENT_RULES:
        pattern = str(rule["pattern"])
        if pattern in text:
            return float(rule["portion_g"]), str(rule["query"])
    # Conservative fallback for unmapped ingredients.
    return 60.0, text


def _is_animal_protein_ingredient(ingredient: str) -> bool:
    text = (ingredient or "").strip().lower()
    return any(marker in text for marker in ANIMAL_PROTEIN_MARKERS)


def _apply_protein_cap(ingredient_rows: List[Dict[str, object]]) -> None:
    total_protein = sum(float(row["protein_g"]) for row in ingredient_rows)
    if total_protein <= 40.0:
        return

    animal_protein = sum(float(row["protein_g"]) for row in ingredient_rows if bool(row["is_animal"]))
    non_animal_protein = total_protein - animal_protein

    if animal_protein > 0:
        target_animal_protein = max(0.0, 40.0 - non_animal_protein)
        scale_factor = min(1.0, target_animal_protein / animal_protein)
        for row in ingredient_rows:
            if bool(row["is_animal"]):
                row["protein_g"] = float(row["protein_g"]) * scale_factor
                row["carbs_g"] = float(row["carbs_g"]) * scale_factor
                row["fat_g"] = float(row["fat_g"]) * scale_factor
                row["calories"] = float(row["calories"]) * scale_factor

    # Safety fallback for meals still above 40g.
    total_protein = sum(float(row["protein_g"]) for row in ingredient_rows)
    if total_protein > 40.0 and total_protein > 0:
        final_scale = 40.0 / total_protein
        for row in ingredient_rows:
            row["protein_g"] = float(row["protein_g"]) * final_scale
            row["carbs_g"] = float(row["carbs_g"]) * final_scale
            row["fat_g"] = float(row["fat_g"]) * final_scale
            row["calories"] = float(row["calories"]) * final_scale


def _apply_calorie_band(ingredient_rows: List[Dict[str, object]], meal_type: str) -> None:
    calories = sum(float(row["calories"]) for row in ingredient_rows)
    meal_type_norm = (meal_type or "").strip().lower()
    if meal_type_norm == "breakfast":
        min_kcal, max_kcal = 350.0, 500.0
    else:
        min_kcal, max_kcal = 400.0, 600.0

    if calories <= 0:
        return
    if min_kcal <= calories <= max_kcal:
        return

    target = min_kcal if calories < min_kcal else max_kcal
    scale = target / calories
    for row in ingredient_rows:
        row["protein_g"] = float(row["protein_g"]) * scale
        row["carbs_g"] = float(row["carbs_g"]) * scale
        row["fat_g"] = float(row["fat_g"]) * scale
        row["calories"] = float(row["calories"]) * scale


def recalculate_meals(meals_path: Path = MEALS_PATH) -> Tuple[int, int]:
    meals = json.loads(meals_path.read_text(encoding="utf-8"))
    cache: Dict[Tuple[str, float], Dict[str, float]] = {}

    meal_count = 0
    ingredient_calls = 0

    for meal in meals:
        ingredient_rows: List[Dict[str, object]] = []

        ingredients = meal.get("ingredients") or []
        for ingredient in ingredients:
            name = str(ingredient).strip()
            if not name:
                continue

            portion_g, usda_query = get_portion_and_query(name)
            cache_key = (usda_query.lower(), portion_g)
            if cache_key not in cache:
                cache[cache_key] = fetch_nutrition_for_ingredient(usda_query, portion_g)
                ingredient_calls += 1

            nutrients = cache[cache_key]

            ingredient_rows.append(
                {
                    "name": name,
                    "is_animal": _is_animal_protein_ingredient(name),
                    "protein_g": float(nutrients["protein_g"]),
                    "carbs_g": float(nutrients["carbs_g"]),
                    "fat_g": float(nutrients["fat_g"]),
                    "calories": float(nutrients["calories"]),
                }
            )

        # Iterate constraints to satisfy both calorie band and protein cap.
        meal_type = str(meal.get("type", "") or "")
        for _ in range(3):
            _apply_protein_cap(ingredient_rows)
            _apply_calorie_band(ingredient_rows, meal_type)

        _apply_protein_cap(ingredient_rows)

        total_protein = sum(float(row["protein_g"]) for row in ingredient_rows)
        total_carbs = sum(float(row["carbs_g"]) for row in ingredient_rows)
        total_fat = sum(float(row["fat_g"]) for row in ingredient_rows)
        total_calories = sum(float(row["calories"]) for row in ingredient_rows)

        meal["protein_g"] = int(round(total_protein))
        meal["carbs_g"] = int(round(total_carbs))
        meal["fat_g"] = int(round(total_fat))
        meal["calories"] = int(round(total_calories))
        meal_count += 1

    meals_path.write_text(json.dumps(meals, indent=2) + "\n", encoding="utf-8")
    return meal_count, ingredient_calls


if __name__ == "__main__":
    updated, api_calls = recalculate_meals()
    print(f"Updated {updated} meals.")
    print(f"USDA API lookups performed: {api_calls}")
