"""
USDA nutrition lookup helpers.

- Searches USDA FoodData Central by ingredient name.
- Picks the first preferred result: Survey (FNDDS), then SR Legacy, then fallback first result.
- Returns macros scaled to a requested gram weight.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import httpx
from dotenv import load_dotenv


load_dotenv()


USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
PREFERRED_DATA_TYPES = ("Survey (FNDDS)", "SR Legacy")


@dataclass
class NutrientsPer100g:
    protein_g: float
    carbs_g: float
    fat_g: float
    calories: float


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def _sanitize_search_query(query: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9 ,.-]", " ", query or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_macros_per_100g(food: Dict[str, Any]) -> NutrientsPer100g:
    """
    Extract core nutrients from USDA food record per 100g.

    Looks for:
    - Protein
    - Carbohydrate, by difference
    - Total lipid (fat)
    - Energy (kcal)
    """
    protein = 0.0
    carbs = 0.0
    fat = 0.0
    calories = 0.0

    nutrients: Iterable[Dict[str, Any]] = food.get("foodNutrients") or []
    for nutrient in nutrients:
        name = _normalize_name(str(nutrient.get("nutrientName", "")))
        value = _safe_float(nutrient.get("value"))

        if name == "protein":
            protein = value
        elif name == "carbohydrate, by difference":
            carbs = value
        elif name == "total lipid (fat)":
            fat = value
        elif name.startswith("energy"):
            # Prefer kcal entry when possible.
            unit = _normalize_name(str(nutrient.get("unitName", "")))
            if unit in {"kcal", "kilocalorie"}:
                calories = value
            elif calories == 0.0:
                calories = value

    return NutrientsPer100g(
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        calories=calories,
    )


def _pick_best_food(foods: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not foods:
        return None

    for preferred in PREFERRED_DATA_TYPES:
        for food in foods:
            if str(food.get("dataType", "")).strip() == preferred:
                return food

    return foods[0]


def fetch_nutrition_for_ingredient(
    ingredient: str,
    weight_g: float,
    api_key: Optional[str] = None,
    timeout_seconds: float = 15.0,
) -> Dict[str, float]:
    """
    Fetch USDA nutrition and scale to weight_g.

    Args:
        ingredient: Ingredient search text, e.g. "chicken breast".
        weight_g: Gram weight to scale nutrients to.
        api_key: USDA API key; defaults to USDA_API_KEY env variable.
        timeout_seconds: HTTP timeout.

    Returns:
        Dict with: protein_g, carbs_g, fat_g, calories

    Raises:
        ValueError: Missing API key, bad args, no USDA result.
        httpx.HTTPError: Network/HTTP errors.
    """
    query = (ingredient or "").strip()
    if not query:
        raise ValueError("ingredient is required")
    if weight_g <= 0:
        raise ValueError("weight_g must be > 0")

    key = api_key or os.getenv("USDA_API_KEY")
    if not key:
        raise ValueError("USDA_API_KEY is missing")

    params = {
        "query": _sanitize_search_query(query),
        "api_key": key,
        "pageSize": 10,
    }

    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.get(USDA_SEARCH_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    foods = payload.get("foods") or []
    best = _pick_best_food(foods)
    if not best:
        raise ValueError(f"No USDA foods found for ingredient: {query}")

    per_100 = _extract_macros_per_100g(best)
    factor = weight_g / 100.0

    return {
        "protein_g": round(per_100.protein_g * factor, 2),
        "carbs_g": round(per_100.carbs_g * factor, 2),
        "fat_g": round(per_100.fat_g * factor, 2),
        "calories": round(per_100.calories * factor, 2),
    }
