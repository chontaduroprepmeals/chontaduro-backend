from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def _call(session_id: str, step: str, answer: dict):
    response = client.post(
        "/next-step",
        json={"session_id": session_id, "step": step, "answer": answer},
    )
    response.raise_for_status()
    return response.json()


def _go_to_review(session_id: str):
    _call(session_id, "start", {})
    _call(session_id, "diet_preference", {"Diet_Preference": "Omnivore"})
    _call(session_id, "pick_plan", {"Plan": "Plan 4: 2 main meals + 1 breakfast (full day)"})
    _call(session_id, "objective", {"Objective": "Lose Fat"})
    _call(
        session_id,
        "allergies_and_restrictions",
        {
            "Selected Allergies": ["Dairy", "Soy"],
            "Any other allergy or note?": "no mushroom",
        },
    )
    _call(
        session_id,
        "personal_info",
        {
            "weight_value": 70,
            "weight_unit": "kg",
            "height_value": 175,
            "height_unit": "cm",
            "age": 30,
            "sex": "Male",
            "days_per_week": "3-4",
            "avg_session_duration": "30-60",
            "intensity": "Moderate",
        },
    )
    return _call(session_id, "duration", {"days": 6})


def test_review_edit_back_navigation_preserves_state():
    session_id = "review-edit-persistence-test"

    first_review = _go_to_review(session_id)
    first_state = first_review["fields"][0]["value"]

    assert first_state["plan_number"] == 4
    assert first_state["objective"] == "Lose Fat"
    assert first_state["weight_value"] == 70.0
    assert first_state["allergies_and_restrictions"] == "dairy, soy | no mushroom"

    for _ in range(5):
        _call(session_id, "back", {})

    second_review = _go_to_review(session_id)
    second_state = second_review["fields"][0]["value"]

    assert second_state["plan_number"] == 4
    assert second_state["objective"] == "Lose Fat"
    assert second_state["weight_value"] == 70.0
    assert second_state["height_value"] == 175.0
    assert second_state["age"] == 30
    assert second_state["allergies_and_restrictions"] == "dairy, soy | no mushroom"
