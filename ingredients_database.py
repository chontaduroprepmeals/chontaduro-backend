"""
Nutritional database for common ingredients.
Values based on USDA FoodData Central.
All values are per 100g unless specified otherwise.
"""

INGREDIENT_DATABASE = {
    # Grains & Cereals
    "oats": {
        "protein_per_100g": 13.2,
        "carbs_per_100g": 66.3,
        "fat_per_100g": 6.9,
        "calories_per_100g": 389,
        "typical_serving_g": 50,
        "unit": "g"
    },
    "white rice": {
        "protein_per_100g": 2.7,
        "carbs_per_100g": 28.2,
        "fat_per_100g": 0.3,
        "calories_per_100g": 130,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "brown rice": {
        "protein_per_100g": 2.6,
        "carbs_per_100g": 23.5,
        "fat_per_100g": 0.9,
        "calories_per_100g": 112,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "quinoa": {
        "protein_per_100g": 4.4,
        "carbs_per_100g": 21.3,
        "fat_per_100g": 1.9,
        "calories_per_100g": 120,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "whole wheat bread": {
        "protein_per_100g": 13.4,
        "carbs_per_100g": 41.3,
        "fat_per_100g": 3.5,
        "calories_per_100g": 247,
        "typical_serving_g": 60,  # 2 slices
        "unit": "g"
    },
    "white pasta": {
        "protein_per_100g": 5.8,
        "carbs_per_100g": 30.9,
        "fat_per_100g": 0.9,
        "calories_per_100g": 158,
        "typical_serving_g": 100,
        "unit": "g"
    },
    "corn tortillas": {
        "protein_per_100g": 5.7,
        "carbs_per_100g": 44.6,
        "fat_per_100g": 2.5,
        "calories_per_100g": 218,
        "typical_serving_g": 60,  # 2 tortillas
        "unit": "g"
    },
    "arepa": {
        "protein_per_100g": 4.5,
        "carbs_per_100g": 38.0,
        "fat_per_100g": 3.5,
        "calories_per_100g": 200,
        "typical_serving_g": 100,
        "unit": "g"
    },

    # Proteins
    "chicken breast": {
        "protein_per_100g": 31.0,
        "carbs_per_100g": 0.0,
        "fat_per_100g": 3.6,
        "calories_per_100g": 165,
        "typical_serving_g": 125,
        "unit": "g"
    },
    "eggs": {
        "protein_per_100g": 12.6,
        "carbs_per_100g": 1.1,
        "fat_per_100g": 9.5,
        "calories_per_100g": 143,
        "typical_serving_g": 100,  # 2 large eggs
        "unit": "g"
    },
    "egg whites": {
        "protein_per_100g": 10.9,
        "carbs_per_100g": 0.7,
        "fat_per_100g": 0.2,
        "calories_per_100g": 52,
        "typical_serving_g": 99,  # 3 egg whites
        "unit": "g"
    },
    "lean ground beef": {
        "protein_per_100g": 26.1,
        "carbs_per_100g": 0.0,
        "fat_per_100g": 10.0,
        "calories_per_100g": 198,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "ground turkey": {
        "protein_per_100g": 27.0,
        "carbs_per_100g": 0.0,
        "fat_per_100g": 8.0,
        "calories_per_100g": 189,
        "typical_serving_g": 148,
        "unit": "g"
    },
    "canned tuna": {
        "protein_per_100g": 29.9,
        "carbs_per_100g": 0.0,
        "fat_per_100g": 0.8,
        "calories_per_100g": 128,
        "typical_serving_g": 130,
        "unit": "g"
    },
    "canned sardines": {
        "protein_per_100g": 24.6,
        "carbs_per_100g": 0.0,
        "fat_per_100g": 11.5,
        "calories_per_100g": 208,
        "typical_serving_g": 160,
        "unit": "g"
    },
    "whole chicken": {
        "protein_per_100g": 27.0,
        "carbs_per_100g": 0.0,
        "fat_per_100g": 14.0,
        "calories_per_100g": 239,
        "typical_serving_g": 148,
        "unit": "g"
    },

    # Dairy
    "regular milk": {
        "protein_per_100ml": 3.4,
        "carbs_per_100ml": 4.8,
        "fat_per_100ml": 3.6,
        "calories_per_100ml": 61,
        "typical_serving_ml": 200,
        "unit": "ml"
    },
    "greek yogurt": {
        "protein_per_100g": 10.0,
        "carbs_per_100g": 3.6,
        "fat_per_100g": 0.4,
        "calories_per_100g": 59,
        "typical_serving_g": 170,
        "unit": "g"
    },
    "fresh cheese": {
        "protein_per_100g": 11.1,
        "carbs_per_100g": 3.4,
        "fat_per_100g": 4.3,
        "calories_per_100g": 98,
        "typical_serving_g": 50,
        "unit": "g"
    },
    "cottage cheese": {
        "protein_per_100g": 11.0,
        "carbs_per_100g": 3.4,
        "fat_per_100g": 4.5,
        "calories_per_100g": 98,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "butter": {
        "protein_per_100g": 0.9,
        "carbs_per_100g": 0.1,
        "fat_per_100g": 81.1,
        "calories_per_100g": 717,
        "typical_serving_g": 10,  # ~1 tbsp
        "unit": "g"
    },

    # Fruits
    "banana": {
        "protein_per_100g": 1.1,
        "carbs_per_100g": 22.8,
        "fat_per_100g": 0.3,
        "calories_per_100g": 89,
        "typical_serving_g": 120,  # 1 medium
        "unit": "g"
    },
    "apple": {
        "protein_per_100g": 0.3,
        "carbs_per_100g": 13.8,
        "fat_per_100g": 0.2,
        "calories_per_100g": 52,
        "typical_serving_g": 180,  # 1 medium
        "unit": "g"
    },
    "ripe plantain": {
        "protein_per_100g": 1.3,
        "carbs_per_100g": 31.9,
        "fat_per_100g": 0.4,
        "calories_per_100g": 122,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "papaya": {
        "protein_per_100g": 0.5,
        "carbs_per_100g": 10.8,
        "fat_per_100g": 0.3,
        "calories_per_100g": 43,
        "typical_serving_g": 150,
        "unit": "g"
    },

    # Vegetables
    "broccoli": {
        "protein_per_100g": 2.8,
        "carbs_per_100g": 7.0,
        "fat_per_100g": 0.4,
        "calories_per_100g": 34,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "spinach": {
        "protein_per_100g": 2.9,
        "carbs_per_100g": 3.6,
        "fat_per_100g": 0.4,
        "calories_per_100g": 23,
        "typical_serving_g": 100,
        "unit": "g"
    },
    "cauliflower": {
        "protein_per_100g": 1.9,
        "carbs_per_100g": 5.0,
        "fat_per_100g": 0.3,
        "calories_per_100g": 25,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "white potato": {
        "protein_per_100g": 2.0,
        "carbs_per_100g": 17.5,
        "fat_per_100g": 0.1,
        "calories_per_100g": 77,
        "typical_serving_g": 200,
        "unit": "g"
    },
    "sweet potato": {
        "protein_per_100g": 1.6,
        "carbs_per_100g": 20.7,
        "fat_per_100g": 0.1,
        "calories_per_100g": 86,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "tomato": {
        "protein_per_100g": 0.9,
        "carbs_per_100g": 3.9,
        "fat_per_100g": 0.2,
        "calories_per_100g": 18,
        "typical_serving_g": 100,
        "unit": "g"
    },
    "onion": {
        "protein_per_100g": 1.1,
        "carbs_per_100g": 9.3,
        "fat_per_100g": 0.1,
        "calories_per_100g": 40,
        "typical_serving_g": 50,
        "unit": "g"
    },
    "garlic": {
        "protein_per_100g": 6.4,
        "carbs_per_100g": 33.1,
        "fat_per_100g": 0.5,
        "calories_per_100g": 149,
        "typical_serving_g": 5,  # 1-2 cloves
        "unit": "g"
    },
    "carrots": {
        "protein_per_100g": 0.9,
        "carbs_per_100g": 9.6,
        "fat_per_100g": 0.2,
        "calories_per_100g": 41,
        "typical_serving_g": 100,
        "unit": "g"
    },
    "cabbage": {
        "protein_per_100g": 1.3,
        "carbs_per_100g": 5.8,
        "fat_per_100g": 0.1,
        "calories_per_100g": 25,
        "typical_serving_g": 150,
        "unit": "g"
    },

    # Legumes
    "black beans": {
        "protein_per_100g": 8.9,
        "carbs_per_100g": 23.7,
        "fat_per_100g": 0.5,
        "calories_per_100g": 132,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "chickpeas": {
        "protein_per_100g": 8.9,
        "carbs_per_100g": 27.4,
        "fat_per_100g": 2.6,
        "calories_per_100g": 164,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "lentils": {
        "protein_per_100g": 9.0,
        "carbs_per_100g": 20.1,
        "fat_per_100g": 0.4,
        "calories_per_100g": 116,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "red beans": {
        "protein_per_100g": 8.7,
        "carbs_per_100g": 22.8,
        "fat_per_100g": 0.5,
        "calories_per_100g": 127,
        "typical_serving_g": 150,
        "unit": "g"
    },
    "bell pepper": {
        "protein_per_100g": 1.0,
        "carbs_per_100g": 6.0,
        "fat_per_100g": 0.3,
        "calories_per_100g": 31,
        "typical_serving_g": 80,
        "unit": "g"
    },
    "cucumber": {
        "protein_per_100g": 0.7,
        "carbs_per_100g": 3.6,
        "fat_per_100g": 0.1,
        "calories_per_100g": 16,
        "typical_serving_g": 100,
        "unit": "g"
    },
    "celery": {
        "protein_per_100g": 0.7,
        "carbs_per_100g": 3.0,
        "fat_per_100g": 0.2,
        "calories_per_100g": 16,
        "typical_serving_g": 50,
        "unit": "g"
    },
    "green beans": {
        "protein_per_100g": 1.8,
        "carbs_per_100g": 7.1,
        "fat_per_100g": 0.1,
        "calories_per_100g": 31,
        "typical_serving_g": 100,
        "unit": "g"
    },
    "zucchini": {
        "protein_per_100g": 1.2,
        "carbs_per_100g": 3.1,
        "fat_per_100g": 0.3,
        "calories_per_100g": 17,
        "typical_serving_g": 100,
        "unit": "g"
    },
    "lettuce": {
        "protein_per_100g": 1.4,
        "carbs_per_100g": 2.9,
        "fat_per_100g": 0.2,
        "calories_per_100g": 17,
        "typical_serving_g": 50,
        "unit": "g"
    },
    "mixed frozen vegetables": {
        "protein_per_100g": 2.5,
        "carbs_per_100g": 10.0,
        "fat_per_100g": 0.2,
        "calories_per_100g": 50,
        "typical_serving_g": 100,
        "unit": "g"
    },
    "soy sauce": {
        "protein_per_100g": 8.1,
        "carbs_per_100g": 4.9,
        "fat_per_100g": 0.1,
        "calories_per_100g": 53,
        "typical_serving_g": 15,  # 1 tbsp
        "unit": "g"
    },
    "honey": {
        "protein_per_100g": 0.3,
        "carbs_per_100g": 82.4,
        "fat_per_100g": 0.0,
        "calories_per_100g": 304,
        "typical_serving_g": 15,  # 1 tbsp
        "unit": "g"
    },
    "simple cereal": {
        "protein_per_100g": 7.0,
        "carbs_per_100g": 80.0,
        "fat_per_100g": 1.5,
        "calories_per_100g": 363,
        "typical_serving_g": 40,
        "unit": "g"
    },
    "rice cereal": {
        "protein_per_100g": 6.5,
        "carbs_per_100g": 84.0,
        "fat_per_100g": 0.5,
        "calories_per_100g": 368,
        "typical_serving_g": 40,
        "unit": "g"
    },

    # Fats & Nuts
    "peanut butter": {
        "protein_per_100g": 25.0,
        "carbs_per_100g": 20.0,
        "fat_per_100g": 50.0,
        "calories_per_100g": 588,
        "typical_serving_g": 32,  # 2 tbsp
        "unit": "g"
    },
    "olive oil": {
        "protein_per_100g": 0.0,
        "carbs_per_100g": 0.0,
        "fat_per_100g": 100.0,
        "calories_per_100g": 884,
        "typical_serving_g": 14,  # 1 tbsp
        "unit": "g"
    },
    "avocado": {
        "protein_per_100g": 2.0,
        "carbs_per_100g": 8.5,
        "fat_per_100g": 14.7,
        "calories_per_100g": 160,
        "typical_serving_g": 100,  # 1/2 medium
        "unit": "g"
    },
    "almonds": {
        "protein_per_100g": 21.2,
        "carbs_per_100g": 21.6,
        "fat_per_100g": 49.9,
        "calories_per_100g": 579,
        "typical_serving_g": 28,  # 1 oz
        "unit": "g"
    },

    # Supplements
    "protein powder": {
        "protein_per_100g": 80.0,
        "carbs_per_100g": 8.0,
        "fat_per_100g": 4.0,
        "calories_per_100g": 400,
        "typical_serving_g": 30,  # 1 scoop
        "unit": "g"
    },
}

# Ingredient aliases for fuzzy matching
INGREDIENT_ALIASES = {
    "oats": ["oatmeal", "rolled oats", "old fashioned oats"],
    "chicken breast": ["chicken", "grilled chicken", "baked chicken", "ground chicken"],
    "eggs": ["egg", "scrambled eggs", "boiled eggs"],
    "regular milk": ["milk", "whole milk"],
    "peanut butter": ["pb", "peanutbutter"],
    "white rice": ["rice"],
    "white pasta": ["pasta", "whole wheat pasta", "spaghetti"],
    "olive oil": ["oil"],
    "white potato": ["potato", "white potatoes", "yellow potatoes"],
    "lean ground beef": ["ground beef"],
    "whole chicken": ["chicken thighs", "chicken leg", "chicken meatballs"],
    "chickpeas": ["garbanzo beans", "garbanzos"],
    "corn tortillas": ["corn tortilla", "flour tortilla"],
    "black beans": ["beans"],
    "red beans": ["kidney beans"],
    "lettuce": ["romaine lettuce", "mixed greens", "spring mix"],
    "bell pepper": ["red bell pepper", "red bell peppers", "green bell pepper", "yellow bell pepper"],
    "lentils": ["lentil"],
    "ripe plantain": ["plantain", "sweet plantain", "sweet plantains"],
    "cauliflower": ["cauliflower rice", "mashed cauliflower"],
    "white potato": ["white potatoes", "yellow potatoes", "mashed potatoes"],
    "carrots": ["carrot"],
    "tomato": ["tomatoes", "cherry tomatoes"],
    "onion": ["red onion"],
    "greek yogurt": ["yogurt"],
    "fresh cheese": ["mozzarella cheese", "cheese"],
}


def find_ingredient(ingredient_name: str) -> str:
    """
    Find ingredient in database, handling aliases and partial matches.
    Returns the canonical ingredient name or None if not found.
    """
    ingredient_lower = ingredient_name.lower().strip()

    # Direct match
    if ingredient_lower in INGREDIENT_DATABASE:
        return ingredient_lower

    # Check aliases
    for canonical_name, aliases in INGREDIENT_ALIASES.items():
        if ingredient_lower in aliases:
            return canonical_name

    # Partial match: check if ingredient_lower is a substring of a db key or vice versa
    for db_ingredient in INGREDIENT_DATABASE.keys():
        if ingredient_lower in db_ingredient or db_ingredient in ingredient_lower:
            return db_ingredient

    return None
