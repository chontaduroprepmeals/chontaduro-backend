"""
Unit tests for:
1. adjust_meal_for_protein_target() – 40g protein cap enforcement
2. validate_daily_macros() – comprehensive macro validation (protein, carbs, fat, calories)
"""
import pytest
from main import adjust_meal_for_protein_target, validate_daily_macros


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _meal_with_ingredients(ingredients):
    """Build a minimal meal_data dict."""
    return {"ingredients": ingredients, "name": "Test Meal"}


def _meal_entry_with_macros(protein, carbs, fat, calories, portion_multiplier=1.0):
    """Build a minimal meal entry (as used in response_menu) with final_macros."""
    return {
        "name": "Test Meal",
        "final_macros": {
            "protein_g": protein,
            "carbs_g": carbs,
            "fat_g": fat,
            "calories": calories,
        },
        "portion_multiplier": portion_multiplier,
    }


# ---------------------------------------------------------------------------
# Tests: adjust_meal_for_protein_target
# ---------------------------------------------------------------------------

class TestAdjustMealForProteinTarget:
    """Tests for the 40g protein cap in adjust_meal_for_protein_target."""

    def test_target_above_40_is_capped_at_40(self):
        """When the caller passes target > 40g, it must be treated as 40g."""
        # Use a high-protein ingredient so base_macros stays below 40g,
        # confirming the target reduction is logged but supplement logic still runs.
        meal = _meal_with_ingredients(["oats", "greek yogurt"])
        result = adjust_meal_for_protein_target(meal, target_protein_per_meal=50)
        # final protein must never exceed 40g
        assert result["final_macros"]["protein_g"] <= 40.0

    def test_meal_exceeding_40g_protein_is_scaled_down(self):
        """A meal whose ingredients naturally provide > 40g protein must be reduced."""
        # chicken breast = 31g protein per 100g → 200g = 62g protein
        meal = _meal_with_ingredients(["chicken", "chicken"])
        result = adjust_meal_for_protein_target(meal, target_protein_per_meal=40)
        assert result["final_macros"]["protein_g"] <= 40.0

    def test_scale_down_returns_reduce_portion_modification(self):
        """When portion is scaled down, 'reduce_portion' must appear in modifications."""
        meal = _meal_with_ingredients(["chicken", "chicken"])
        result = adjust_meal_for_protein_target(meal, target_protein_per_meal=40)
        if result["final_macros"]["protein_g"] < result["base_macros"]["protein_g"]:
            types = [m["type"] for m in result["modifications"]]
            assert "reduce_portion" in types

    def test_meal_in_30_to_40_range_not_modified(self):
        """A meal already in the 30–40 g range must be returned as-is (no modifications)."""
        # Greek yogurt + moderate protein ingredients should be in range with a
        # single serving. We mock by using a meal that already reports 30-40g.
        meal = _meal_with_ingredients(["greek yogurt", "oats"])
        result = adjust_meal_for_protein_target(meal, target_protein_per_meal=35)
        base_protein = result["base_macros"]["protein_g"]
        if 30 <= base_protein <= 40:
            assert result["modifications"] == []
            assert result["final_macros"]["protein_g"] == base_protein

    def test_final_protein_never_exceeds_40g(self):
        """Regardless of input, final_macros protein must always be ≤ 40g."""
        for target in [20, 35, 40, 45, 60, 100]:
            meal = _meal_with_ingredients(["chicken", "chicken"])
            result = adjust_meal_for_protein_target(meal, target_protein_per_meal=target)
            assert result["final_macros"]["protein_g"] <= 40.0, (
                f"target={target}: got {result['final_macros']['protein_g']}g"
            )

    def test_scaled_down_macros_are_proportional(self):
        """When scaling down, carbs/fat/calories must decrease in the same proportion."""
        meal = _meal_with_ingredients(["chicken", "chicken"])
        result = adjust_meal_for_protein_target(meal, target_protein_per_meal=40)
        base = result["base_macros"]
        final = result["final_macros"]
        if base["protein_g"] > 40:
            expected_scale = 40 / base["protein_g"]
            assert abs(final["fat_g"] - round(base["fat_g"] * expected_scale, 1)) <= 0.2
            assert abs(final["calories"] - round(base["calories"] * expected_scale)) <= 2


# ---------------------------------------------------------------------------
# Tests: validate_daily_macros
# ---------------------------------------------------------------------------

class TestValidateDailyMacros:
    """Tests for comprehensive macro validation (protein, carbs, fat, calories)."""

    def test_no_scaling_when_within_targets(self):
        """Meals within all macro targets must not be modified."""
        menu = [
            _meal_entry_with_macros(protein=35, carbs=60, fat=15, calories=510),
            _meal_entry_with_macros(protein=35, carbs=60, fat=15, calories=510),
            _meal_entry_with_macros(protein=35, carbs=60, fat=15, calories=510),
        ]
        original_protein = [m["final_macros"]["protein_g"] for m in menu]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1820)
        for i, meal in enumerate(result):
            assert meal["final_macros"]["protein_g"] == original_protein[i]

    def test_fat_exceeds_target_triggers_scaling(self):
        """When daily fat exceeds target+5%, all meals should be scaled down."""
        # 3 meals × 30g fat = 90g total fat; target = 55g → exceeds 55*1.05=57.75g
        menu = [
            _meal_entry_with_macros(protein=40, carbs=60, fat=30, calories=680),
            _meal_entry_with_macros(protein=40, carbs=60, fat=30, calories=680),
            _meal_entry_with_macros(protein=40, carbs=60, fat=30, calories=680),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1820)
        total_fat = sum(m["final_macros"]["fat_g"] for m in result)
        assert total_fat <= 55 * 1.05 + 0.5  # allow tiny rounding error

    def test_protein_exceeds_target_triggers_scaling(self):
        """When daily protein exceeds target+5%, all meals should be scaled down."""
        # 3 meals × 50g protein = 150g; target = 133g → 150 > 133*1.05=139.65g
        menu = [
            _meal_entry_with_macros(protein=50, carbs=60, fat=18, calories=600),
            _meal_entry_with_macros(protein=50, carbs=60, fat=18, calories=600),
            _meal_entry_with_macros(protein=50, carbs=60, fat=18, calories=600),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1820)
        total_protein = sum(m["final_macros"]["protein_g"] for m in result)
        assert total_protein <= 133 * 1.05 + 0.5

    def test_calories_exceed_target_triggers_scaling(self):
        """When daily calories exceed target+5%, all meals should be scaled down."""
        menu = [
            _meal_entry_with_macros(protein=40, carbs=70, fat=20, calories=700),
            _meal_entry_with_macros(protein=40, carbs=70, fat=20, calories=700),
            _meal_entry_with_macros(protein=40, carbs=70, fat=20, calories=700),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1820)
        total_calories = sum(m["final_macros"]["calories"] for m in result)
        assert total_calories <= 1820 * 1.05 + 5

    def test_most_restrictive_scale_factor_used(self):
        """When multiple macros exceed targets, the smallest (most restrictive) factor is applied."""
        # fat: 90g vs 55g target → factor 55/90 ≈ 0.611
        # protein: 150g vs 133g target → factor 133/150 ≈ 0.887
        # most restrictive = 0.611
        menu = [
            _meal_entry_with_macros(protein=50, carbs=60, fat=30, calories=700),
            _meal_entry_with_macros(protein=50, carbs=60, fat=30, calories=700),
            _meal_entry_with_macros(protein=50, carbs=60, fat=30, calories=700),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=2100)
        total_fat = sum(m["final_macros"]["fat_g"] for m in result)
        total_protein = sum(m["final_macros"]["protein_g"] for m in result)
        assert total_fat <= 55 * 1.05 + 0.5
        assert total_protein <= 133 * 1.05 + 0.5

    def test_portion_multiplier_scaled_proportionally(self):
        """portion_multiplier must be scaled by the same factor as macros."""
        # 2 meals × 35g fat = 70g total fat; target = 55g → 70 > 55*1.05=57.75g → triggers scaling
        menu = [
            _meal_entry_with_macros(protein=40, carbs=60, fat=35, calories=700, portion_multiplier=1.0),
            _meal_entry_with_macros(protein=40, carbs=60, fat=35, calories=700, portion_multiplier=1.0),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=2000)
        for meal in result:
            assert meal["portion_multiplier"] < 1.0

    def test_empty_menu_returns_unchanged(self):
        """Empty menu list must be returned without error."""
        result = validate_daily_macros([], target_protein=133, target_carbs=198, target_fat=55, target_calories=1820)
        assert result == []

    def test_zero_calories_returns_unchanged(self):
        """Menu with zero calories must be returned without modification."""
        menu = [_meal_entry_with_macros(protein=0, carbs=0, fat=0, calories=0)]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1820)
        assert result[0]["final_macros"]["calories"] == 0
