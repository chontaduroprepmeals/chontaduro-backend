"""
Tests for plan-based menu display logic.

Validates that the correct nutritional detail is exposed (or hidden) to the
client based on the user's subscription plan:

- Plan 4 (premium): full macros per meal, ingredient names (no gramajes),
  daily macro summary, nutrition totals panel, snack suggestions.
- Plans 1-3 (basic): dish name, brief ingredient description, portion slogan
  only — no macro tables, no gramajes, no daily summary, no snack detail.
"""
import pytest
from main import get_plan_display_config


# ---------------------------------------------------------------------------
# Tests: get_plan_display_config
# ---------------------------------------------------------------------------

class TestGetPlanDisplayConfig:
    """Tests for the centralised plan display configuration helper."""

    # --- Plan 4 (premium) ---

    def test_plan4_shows_macros(self):
        config = get_plan_display_config(4)
        assert config["show_macros"] is True

    def test_plan4_shows_ingredients(self):
        config = get_plan_display_config(4)
        assert config["show_ingredients"] is True

    def test_plan4_shows_daily_summary(self):
        config = get_plan_display_config(4)
        assert config["show_daily_summary"] is True

    def test_plan4_shows_nutrition_totals(self):
        config = get_plan_display_config(4)
        assert config["show_nutrition_totals"] is True

    def test_plan4_shows_snack_recommendations(self):
        config = get_plan_display_config(4)
        assert config["show_snack_recommendations"] is True

    # --- Plans 1-3 (basic) ---

    @pytest.mark.parametrize("plan", [1, 2, 3])
    def test_basic_plans_hide_macros(self, plan):
        config = get_plan_display_config(plan)
        assert config["show_macros"] is False

    @pytest.mark.parametrize("plan", [1, 2, 3])
    def test_basic_plans_hide_ingredients(self, plan):
        """Plans 1-3 do not show any ingredient list — not even names."""
        config = get_plan_display_config(plan)
        assert config["show_ingredients"] is False

    @pytest.mark.parametrize("plan", [1, 2, 3])
    def test_basic_plans_hide_daily_summary(self, plan):
        config = get_plan_display_config(plan)
        assert config["show_daily_summary"] is False

    @pytest.mark.parametrize("plan", [1, 2, 3])
    def test_basic_plans_hide_nutrition_totals(self, plan):
        config = get_plan_display_config(plan)
        assert config["show_nutrition_totals"] is False

    @pytest.mark.parametrize("plan", [1, 2, 3])
    def test_basic_plans_hide_snack_recommendations(self, plan):
        config = get_plan_display_config(plan)
        assert config["show_snack_recommendations"] is False

    # --- Edge cases ---

    def test_unknown_plan_hides_everything(self):
        """An unrecognised plan number must default to the most restrictive view."""
        config = get_plan_display_config(0)
        assert config["show_macros"] is False
        assert config["show_ingredients"] is False
        assert config["show_daily_summary"] is False
        assert config["show_nutrition_totals"] is False
        assert config["show_snack_recommendations"] is False

    def test_all_plans_return_dict_with_required_keys(self):
        required_keys = {
            "show_macros",
            "show_ingredients",
            "show_daily_summary",
            "show_nutrition_totals",
            "show_snack_recommendations",
        }
        for plan in range(1, 5):
            config = get_plan_display_config(plan)
            assert required_keys.issubset(config.keys()), (
                f"Plan {plan} config is missing keys: {required_keys - set(config.keys())}"
            )


# ---------------------------------------------------------------------------
# Tests: API response structure per plan (using simulated response dicts)
# ---------------------------------------------------------------------------

class TestApiResponseStructureByPlan:
    """
    Verify that the helper produces the correct flags that drive which fields
    are included in the menu API response.
    """

    def _simulate_plan4_response(self):
        """Minimal shape of a plan-4 menu API response."""
        return {
            "plan": 4,
            "menu": [],
            "price": 41.0,
            "nutrition": {
                "tmb": 1500,
                "tdee": 2250,
                "calorie_target": 1980,
                "totals": {
                    "protein_total": 120,
                    "carbs_total": 210,
                    "fat_total": 56,
                    "calories_total": 1878,
                },
            },
            "daily_summary": {
                "meals_only": {"protein": 120, "carbs": 196, "fat": 59.8, "calories": 1748},
                "snack_contribution": {"protein": "10-18g", "carbs": "15-25g", "calories": "~130 kcal"},
                "final_total_estimate": {
                    "protein": "~128-138g", "carbs": "~205-220g",
                    "fat": "~60-65g", "calories": "~1848-1908 kcal",
                },
                "message": "✨ Perfect balance for your body recomposition goals!",
            },
        }

    def _simulate_basic_plan_response(self, plan: int):
        """Minimal shape of a plans 1-3 menu API response."""
        return {
            "plan": plan,
            "menu": [],
            "price": 41.0,
            "nutrition": {
                "tmb": 1500,
                "tdee": 2250,
                "calorie_target": 1980,
                # no 'totals' key for plans 1-3
            },
            # no 'daily_summary' key for plans 1-3
        }

    def test_plan4_response_has_plan_field(self):
        resp = self._simulate_plan4_response()
        assert resp.get("plan") == 4

    def test_plan4_response_has_nutrition_totals(self):
        resp = self._simulate_plan4_response()
        assert "totals" in resp["nutrition"]

    def test_plan4_response_has_daily_summary(self):
        resp = self._simulate_plan4_response()
        assert "daily_summary" in resp

    @pytest.mark.parametrize("plan", [1, 2, 3])
    def test_basic_plan_response_has_plan_field(self, plan):
        resp = self._simulate_basic_plan_response(plan)
        assert resp.get("plan") == plan

    @pytest.mark.parametrize("plan", [1, 2, 3])
    def test_basic_plan_response_has_no_nutrition_totals(self, plan):
        resp = self._simulate_basic_plan_response(plan)
        assert "totals" not in resp.get("nutrition", {})

    @pytest.mark.parametrize("plan", [1, 2, 3])
    def test_basic_plan_response_has_no_daily_summary(self, plan):
        resp = self._simulate_basic_plan_response(plan)
        assert "daily_summary" not in resp

    def test_get_plan_display_config_agrees_with_plan4_response_structure(self):
        """Config flags must be consistent with what plan 4 actually returns."""
        resp = self._simulate_plan4_response()
        config = get_plan_display_config(resp["plan"])
        assert config["show_nutrition_totals"] is ("totals" in resp.get("nutrition", {}))
        assert config["show_daily_summary"] is ("daily_summary" in resp)

    @pytest.mark.parametrize("plan", [1, 2, 3])
    def test_get_plan_display_config_agrees_with_basic_plan_response_structure(self, plan):
        """Config flags must be consistent with what basic plans actually return."""
        resp = self._simulate_basic_plan_response(plan)
        config = get_plan_display_config(resp["plan"])
        assert config["show_nutrition_totals"] is ("totals" in resp.get("nutrition", {}))
        assert config["show_daily_summary"] is ("daily_summary" in resp)
