"""
Unit tests for:
1. adjust_meal_for_protein_target() – 40g protein cap/floor enforcement
2. validate_daily_macros() – comprehensive macro validation (protein, carbs, fat, calories)
3. generate_flexible_snack_message() – snack guidance carb range
"""
import pytest
from main import adjust_meal_for_protein_target, validate_daily_macros, generate_flexible_snack_message


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

    def test_reduce_portion_modification_is_internal(self):
        """The 'reduce_portion' modification must be internal (no 'display' field shown to customer)."""
        meal = _meal_with_ingredients(["chicken", "chicken"])
        result = adjust_meal_for_protein_target(meal, target_protein_per_meal=40)
        for mod in result["modifications"]:
            if mod["type"] == "reduce_portion":
                assert "display" not in mod, "reduce_portion must not have a 'display' field (internal only)"
                assert mod.get("internal") is True, "reduce_portion must have internal=True"
                assert "note" in mod, "reduce_portion must have a 'note' field for backend logging"

    def test_meal_near_40g_but_under_is_supplemented(self):
        """A supplement-compatible meal with 30-39g protein must be supplemented toward 40g."""
        # greek yogurt + oats + eggs gives ~36g protein (supplement-compatible, no no_supplement ingredients)
        meal = _meal_with_ingredients(["greek yogurt", "oats", "eggs"])
        result = adjust_meal_for_protein_target(meal, target_protein_per_meal=40)
        base_protein = result["base_macros"]["protein_g"]
        if 30 <= base_protein < 40:
            # Should have been supplemented — modifications non-empty or protein increased
            assert (
                len(result["modifications"]) > 0
                or result["final_macros"]["protein_g"] > base_protein
            ), f"Expected supplement for {base_protein}g meal; got {result['final_macros']['protein_g']}g"

    def test_incompatible_meal_under_40g_scaled_up(self):
        """An incompatible meal (tuna+rice) with <40g protein must be scaled up to 40g internally."""
        # tuna + rice gives ~34g protein; tuna is in the no_supplement list
        meal = _meal_with_ingredients(["tuna", "rice"])
        result = adjust_meal_for_protein_target(meal, target_protein_per_meal=40)
        base_protein = result["base_macros"]["protein_g"]
        if base_protein < 40:
            assert result["final_macros"]["protein_g"] == 40.0, (
                f"Expected 40g after scale-up of {base_protein}g incompatible meal; "
                f"got {result['final_macros']['protein_g']}g"
            )
            # No visible display modifications (internal portion adjustment only)
            assert not any(m.get("display") for m in result["modifications"])

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
        """When daily fat exceeds 110% of target, scaling is triggered.

        With the single-pass conservative approach, the MOST CONSERVATIVE factor
        (closest to 1.0) is applied once.  When calories are ALSO over target, the
        calorie factor is more conservative than the fat factor, so it is chosen.
        Calories are brought within range; fat is reduced but may not fully reach the
        fat-specific limit in a single pass — that is intentional to prevent oscillation.
        """
        # 3 meals × 30g fat = 90g total fat; target = 55g → total 90g exceeds max allowed 60.5g (110%)
        # 3 meals × 680 kcal = 2040 total; target = 1820 → also exceeds max allowed 1965.6 kcal (108%)
        # Conservative factor: calorie factor 0.892 vs fat factor 0.611 → 0.892 applied
        menu = [
            _meal_entry_with_macros(protein=40, carbs=60, fat=30, calories=680),
            _meal_entry_with_macros(protein=40, carbs=60, fat=30, calories=680),
            _meal_entry_with_macros(protein=40, carbs=60, fat=30, calories=680),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1820)
        total_fat = sum(m["final_macros"]["fat_g"] for m in result)
        total_calories = sum(m["final_macros"]["calories"] for m in result)
        # Fat must be reduced from the original 90g (some scaling occurred)
        assert total_fat < 90, f"Expected fat to be reduced from 90g, got {total_fat:.1f}g"
        # Calories must be within the acceptable range after the single-pass scaling
        assert total_calories <= 1820 * 1.08 + 5, f"Expected calories ≤ {1820 * 1.08 + 5:.0f}, got {total_calories}"

    def test_protein_not_scaled_even_when_exceeding_target(self):
        """Protein must NOT be scaled down even when it exceeds target.
        Protein is already enforced at 30-40g per meal by adjust_meal_for_protein_target.
        Double-scaling would violate Issue 2 requirements."""
        # 3 meals × 50g protein = 150g; target = 133g → would trigger scaling in old code
        menu = [
            _meal_entry_with_macros(protein=50, carbs=60, fat=18, calories=600),
            _meal_entry_with_macros(protein=50, carbs=60, fat=18, calories=600),
            _meal_entry_with_macros(protein=50, carbs=60, fat=18, calories=600),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1820)
        total_protein = sum(m["final_macros"]["protein_g"] for m in result)
        # Protein should NOT be reduced regardless of whether it exceeds target
        assert total_protein == 150, f"Protein was unexpectedly scaled: got {total_protein}g instead of 150g"

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

    def test_most_restrictive_scale_factor_used_for_fat(self):
        """When fat exceeds target, the scale factor is applied to fat/carbs/calories (NOT protein)."""
        # fat: 90g vs 55g target → factor 55/90 ≈ 0.611
        # protein stays unchanged (no protein scaling)
        menu = [
            _meal_entry_with_macros(protein=50, carbs=60, fat=30, calories=700),
            _meal_entry_with_macros(protein=50, carbs=60, fat=30, calories=700),
            _meal_entry_with_macros(protein=50, carbs=60, fat=30, calories=700),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=2100)
        total_fat = sum(m["final_macros"]["fat_g"] for m in result)
        total_protein = sum(m["final_macros"]["protein_g"] for m in result)
        # Fat should be scaled down
        assert total_fat <= 55 * 1.05 + 0.5
        # Protein must NOT be scaled (stays at original 150g)
        assert total_protein == 150, f"Protein was unexpectedly scaled: got {total_protein}g"

    def test_portion_multiplier_scaled_proportionally(self):
        """portion_multiplier must be scaled by the same factor as macros when scaling DOWN."""
        # 2 meals × 35g fat = 70g total fat; target = 55g → 70 > 55*1.05=57.75g → triggers scale-down
        # Use calories = ~1000 kcal/meal so total (2000) is within the calorie target range (2000±5%)
        menu = [
            _meal_entry_with_macros(protein=40, carbs=131, fat=35, calories=1000, portion_multiplier=1.0),
            _meal_entry_with_macros(protein=40, carbs=131, fat=35, calories=1000, portion_multiplier=1.0),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=2000)
        for meal in result:
            assert meal["portion_multiplier"] < 1.0

    def test_calories_too_low_triggers_scale_up(self):
        """When daily calories are below 95% of target, meals must be scaled UP."""
        # 3 meals × 360 kcal = 1080 kcal; target = 1650 → way below → scale up
        menu = [
            _meal_entry_with_macros(protein=40, carbs=30, fat=10, calories=360, portion_multiplier=0.8),
            _meal_entry_with_macros(protein=40, carbs=30, fat=10, calories=360, portion_multiplier=0.8),
            _meal_entry_with_macros(protein=40, carbs=30, fat=10, calories=360, portion_multiplier=0.8),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1650)
        total_calories = sum(m["final_macros"]["calories"] for m in result)
        # After scaling up, calories should be at or near target (within 5%)
        assert total_calories >= 1650 * 0.95 - 5, f"Expected ~1650 kcal, got {total_calories}"

    def test_scale_up_does_not_touch_protein(self):
        """When scaling up for low calories, protein must NOT be increased."""
        menu = [
            _meal_entry_with_macros(protein=40, carbs=20, fat=8, calories=300),
            _meal_entry_with_macros(protein=40, carbs=20, fat=8, calories=300),
            _meal_entry_with_macros(protein=40, carbs=20, fat=8, calories=300),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1650)
        total_protein = sum(m["final_macros"]["protein_g"] for m in result)
        # Protein must NOT be scaled up (stays at original 120g)
        assert total_protein == 120, f"Protein was unexpectedly scaled: got {total_protein}g"

    def test_portion_multiplier_scaled_up_proportionally(self):
        """portion_multiplier must be scaled UP by the same factor when calories are too low."""
        menu = [
            _meal_entry_with_macros(protein=40, carbs=20, fat=8, calories=300, portion_multiplier=0.7),
            _meal_entry_with_macros(protein=40, carbs=20, fat=8, calories=300, portion_multiplier=0.7),
            _meal_entry_with_macros(protein=40, carbs=20, fat=8, calories=300, portion_multiplier=0.7),
        ]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1650)
        for meal in result:
            assert meal["portion_multiplier"] > 0.7

    def test_empty_menu_returns_unchanged(self):
        """Empty menu list must be returned without error."""
        result = validate_daily_macros([], target_protein=133, target_carbs=198, target_fat=55, target_calories=1820)
        assert result == []

    def test_zero_calories_returns_unchanged(self):
        """Menu with zero calories must be returned without modification."""
        menu = [_meal_entry_with_macros(protein=0, carbs=0, fat=0, calories=0)]
        result = validate_daily_macros(menu, target_protein=133, target_carbs=198, target_fat=55, target_calories=1820)
        assert result[0]["final_macros"]["calories"] == 0


# ---------------------------------------------------------------------------
# Tests: generate_flexible_snack_message
# ---------------------------------------------------------------------------

class TestGenerateFlexibleSnackMessage:
    """Tests for proper snack guidance ranges, especially carb range."""

    def test_carb_range_always_shows_spread_when_gap_is_zero(self):
        """When carbs_gap is 0, carbs_max must still be greater than carbs_min."""
        result = generate_flexible_snack_message(
            protein_gap=13, carbs_gap=0, fat_gap=0, calories_gap=170
        )
        carbs_range = result["carbs_range"]  # e.g. "10-20g"
        parts = carbs_range.replace("g", "").split("-")
        carbs_min = int(parts[0])
        carbs_max = int(parts[1])
        assert carbs_max > carbs_min, (
            f"Expected carbs_max > carbs_min when gap=0, got '{carbs_range}'"
        )

    def test_carb_range_never_shows_equal_min_max(self):
        """Carb range must never show 'X-Xg' (min == max)."""
        for gap in [0, 5, 10, 15, 20]:
            result = generate_flexible_snack_message(
                protein_gap=13, carbs_gap=gap, fat_gap=3, calories_gap=170
            )
            parts = result["carbs_range"].replace("g", "").split("-")
            carbs_min = int(parts[0])
            carbs_max = int(parts[1])
            assert carbs_max > carbs_min, (
                f"carbs_gap={gap}: expected spread, got '{result['carbs_range']}'"
            )

    def test_carb_range_reasonable_when_gap_is_normal(self):
        """With a normal carbs_gap (e.g. 15g), the range should span at least 10g."""
        result = generate_flexible_snack_message(
            protein_gap=13, carbs_gap=15, fat_gap=5, calories_gap=170
        )
        parts = result["carbs_range"].replace("g", "").split("-")
        spread = int(parts[1]) - int(parts[0])
        assert spread >= 10, f"Expected ≥10g spread, got {spread}g"
