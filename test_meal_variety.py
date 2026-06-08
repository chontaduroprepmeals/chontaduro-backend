"""
Unit tests for meal variety tracking in generate_menu().
Verifies that:
- No meal repeats within the same day
- Meals are varied across days within the variety_window
- Graceful fallback when not enough unique meals exist
"""
import pytest
from main import (
    SPECIAL_VEG_PAIRING_NAMES,
    _is_animal_protein_meal,
    generate_menu,
    SessionState,
    filter_meals,
)


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

    def test_no_duplicate_day_meal_combinations_across_week_plan4(self):
        """Every day must have a unique combination of meals across the week."""
        state = _make_state(plan=4, days=7)
        menu = generate_menu(state, protein_per_meal=35, calories_per_meal=600, variety_window=3)
        names = [m.name for m in menu]
        meals_per_day = 3

        day_signatures = []
        for day in range(state.days):
            day_names = names[day * meals_per_day : (day + 1) * meals_per_day]
            day_signatures.append(tuple(sorted(day_names)))

        assert len(day_signatures) == len(set(day_signatures)), (
            f"Duplicate day combinations found: {day_signatures}"
        )


class TestMealPoolExclusions:
    """Ensure explicitly excluded high-density meals are never selected."""

    def test_excluded_high_density_meals_not_in_filtered_pool(self):
        meals = filter_meals(dislikes=[], allergies=[], dietary_restrictions=[], diet=None)
        names = {m.name.strip().lower() for m in meals}
        assert "lentil stew with rice" not in names
        assert "black bean rice bowl" not in names


class TestStrictMainMealAnimalProteinPolicy:
    """Lunch/dinner (main meal) must always have allowed animal protein."""

    def test_main_meals_all_have_allowed_animal_protein(self):
        meals = filter_meals(dislikes=[], allergies=[], dietary_restrictions=[], diet=None)
        mains = [m for m in meals if m.type.lower() == "main meal"]

        disallowed_names = {
            "chickpea curry with brown rice",
            "red beans and rice",
            "lentil stew with rice",
            "black bean rice bowl",
            "egg fried rice with mixed vegetables",
            "egg and potato hash",
            "lentil and vegetable soup with bread",
            "black bean and sweet plantain bowl",
            "pasta with white beans and spinach",
            "red bean and rice burrito",
        }

        main_names = {m.name.strip().lower() for m in mains}
        assert not (main_names.intersection(disallowed_names)), (
            f"Found non-compliant main meals: {sorted(main_names.intersection(disallowed_names))}"
        )

    def test_breakfast_pool_stays_flexible(self):
        meals = filter_meals(dislikes=[], allergies=[], dietary_restrictions=[], diet=None)
        breakfasts = [m.name.strip().lower() for m in meals if m.type.lower() == "breakfast"]
        assert "oatmeal with banana and peanut butter" in breakfasts
        assert "greek yogurt with apple and granola" in breakfasts


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


class TestOmnivoreDailyPairingRules:
    """Omnivore and No Red Meat plans must include animal-protein pairing constraints."""

    @pytest.mark.parametrize("diet", ["omnivore", "no red meat"])
    def test_no_two_vegetarian_meals_per_day(self, diet):
        state = _make_state(plan=4, days=7)
        state.diet_preference = diet

        menu = generate_menu(state, protein_per_meal=35, calories_per_meal=600, variety_window=3)
        meals_per_day = 3

        for day in range(state.days):
            day_slice = menu[day * meals_per_day : (day + 1) * meals_per_day]
            vegetarian_count = sum(1 for m in day_slice if not _is_animal_protein_meal(m))
            assert vegetarian_count <= 1, (
                f"Day {day + 1} has too many vegetarian meals for diet={diet}: "
                f"{[m.name for m in day_slice]}"
            )

    @pytest.mark.parametrize("diet", ["omnivore", "no red meat"])
    def test_special_legume_meals_not_together_and_paired_with_animal(self, diet):
        state = _make_state(plan=4, days=7)
        state.diet_preference = diet

        menu = generate_menu(state, protein_per_meal=35, calories_per_meal=600, variety_window=3)
        meals_per_day = 3

        for day in range(state.days):
            day_slice = menu[day * meals_per_day : (day + 1) * meals_per_day]
            day_names = {m.name.strip().lower() for m in day_slice}
            day_has_special = any(name in SPECIAL_VEG_PAIRING_NAMES for name in day_names)
            day_has_animal = any(_is_animal_protein_meal(m) for m in day_slice)

            # Never include both special vegetarian meals in the same day.
            assert not (
                "chickpea curry with brown rice" in day_names
                and "red beans and rice" in day_names
            ), f"Day {day + 1} contains both special meals: {[m.name for m in day_slice]}"

            # If one of these appears, ensure at least one animal-protein meal is present.
            if day_has_special:
                assert day_has_animal, (
                    f"Day {day + 1} has special vegetarian meal without animal pairing: "
                    f"{[m.name for m in day_slice]}"
                )
