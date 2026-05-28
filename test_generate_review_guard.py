from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_generate_menu_requires_review_step():
    session_id = "guard-generate-review"

    response = client.post(
        "/next-step",
        json={
            "session_id": session_id,
            "step": "review",
            "answer": {},
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "invalid_generate_step"
    assert body["expected_step"] == "review"
    assert body["current_step"] == "start"
