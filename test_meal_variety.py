"""
Unit tests for meal variety tracking in generate_menu().
Verifies that:
- No meal repeats within the same day
- Meals are varied across days within the variety_window
- Graceful fallback when not enough unique meals exist
"""
import pytest
from main import generate_menu, SessionState


def _make_state(plan: int, days: int) -> SessionState:
    state = SessionState()
    state.plan = plan
    state.days = days
    state.dislikes = []
    state.allergies = []
    state.dietary_restrictions = []
    state.diet_preference = None
    state.template_id = None
    return state


class TestNoSameDayRepeats:
    """Meals within the same day must always be unique."""

    def test_plan2_no_same_day_duplicates(self):
        """Plan 2 = 2 main meals per day; neither meal should be repeated."""
        state = _make_state(plan=2, days=3)
        menu = generate_menu(state, protein_per_meal=35, calories_per_meal=600, variety_window=3)
        names = [m.name for m in menu]
        meals_per_day = 2
        for day in range(state.days):
            day_names = names[day * meals_per_day : (day + 1) * meals_per_day]
            assert len(day_names) == len(set(day_names)), (
                f"Day {day + 1} has duplicate meals: {day_names}"
            )

    def test_plan4_no_same_day_duplicates(self):
        """Plan 4 = 2 main meals + 1 breakfast per day; none should repeat in a day."""
        state = _make_state(plan=4, days=3)
        menu = generate_menu(state, protein_per_meal=35, calories_per_meal=600, variety_window=3)
        names = [m.name for m in menu]
        meals_per_day = 3  # num_main=2, num_break=1
        for day in range(state.days):
            day_names = names[day * meals_per_day : (day + 1) * meals_per_day]
            assert len(day_names) == len(set(day_names)), (
                f"Day {day + 1} has duplicate meals: {day_names}"
            )


class TestVarietyAcrossDays:
    """Meals should vary across days within the variety window."""

    def test_three_day_menu_all_unique(self):
        """For a 3-day menu with enough meals in the database, all meals should be unique."""
        state = _make_state(plan=2, days=3)
        menu = generate_menu(state, protein_per_meal=35, calories_per_meal=600, variety_window=3)
        names = [m.name for m in menu]
        # Given the database has many meals, all 6 should be unique
        assert len(names) == len(set(names)), f"Duplicate meals found: {names}"

    def test_correct_total_meals_returned(self):
        """generate_menu must return exactly days × meals_per_day meals."""
        state = _make_state(plan=2, days=3)
        menu = generate_menu(state, protein_per_meal=35, calories_per_meal=600, variety_window=3)
        assert len(menu) == 6, f"Expected 6 meals, got {len(menu)}"

    def test_variety_window_parameter_accepted(self):
        """generate_menu must accept variety_window parameter without error."""
        state = _make_state(plan=1, days=3)
        menu = generate_menu(state, protein_per_meal=35, calories_per_meal=600, variety_window=3)
        assert len(menu) == 3


class TestEdgeCases:
    """Edge cases: missing data, 0 days, etc."""

    def test_no_plan_returns_empty(self):
        state = _make_state(plan=None, days=3)  # type: ignore[arg-type]
        menu = generate_menu(state)
        assert menu == []

    def test_no_days_returns_empty(self):
        state = _make_state(plan=2, days=None)  # type: ignore[arg-type]
        menu = generate_menu(state)
        assert menu == []

    def test_default_variety_window(self):
        """Calling without variety_window should still work (defaults to 3)."""
        state = _make_state(plan=2, days=3)
        menu = generate_menu(state, protein_per_meal=35, calories_per_meal=600)
        assert len(menu) == 6
