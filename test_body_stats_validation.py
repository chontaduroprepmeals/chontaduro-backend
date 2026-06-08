from fastapi.testclient import TestClient

from main import app, sessions, validate_body_stats_input


client = TestClient(app)


def test_validate_body_stats_input_rejects_out_of_range_values():
    result = validate_body_stats_input(
        weight=35,
        weight_unit="kg",
        height=130,
        height_unit="cm",
        age=12,
    )
    assert result["valid"] is False
    assert "Weight must be between 40 and 150 kg" in result["warning"]
    assert "Height must be between 140 and 220 cm" in result["warning"]
    assert "Age must be between 16 and 80" in result["warning"]


def test_validate_body_stats_input_accepts_valid_lbs_inches_values():
    result = validate_body_stats_input(
        weight=180,
        weight_unit="lbs",
        height=70,
        height_unit="in",
        age=30,
    )
    assert result["valid"] is True


def test_next_step_personal_info_blocks_invalid_ranges_with_warning():
    sessions.clear()
    session_id = "test-body-stats-invalid"

    response = client.post(
        "/next-step",
        json={
            "session_id": session_id,
            "step": "personal_info",
            "answer": {
                "weight": 35,
                "weight_unit": "kg",
                "height": 130,
                "height_unit": "cm",
                "age": 15,
                "sex": "male",
                "days_per_week": "3-4",
                "avg_session_duration": "30-60",
                "intensity": "moderate",
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data.get("current_step") == "personal_info"
    assert "warning" in data
    assert "Some values look unrealistic" in data["warning"]


def test_next_step_personal_info_allows_valid_ranges():
    sessions.clear()
    session_id = "test-body-stats-valid"

    response = client.post(
        "/next-step",
        json={
            "session_id": session_id,
            "step": "personal_info",
            "answer": {
                "weight": 70,
                "weight_unit": "kg",
                "height": 175,
                "height_unit": "cm",
                "age": 30,
                "sex": "female",
                "days_per_week": "3-4",
                "avg_session_duration": "30-60",
                "intensity": "moderate",
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data.get("current_step") == "duration"
