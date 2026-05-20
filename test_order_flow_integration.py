"""
Integration tests for the new post-menu order flow.
Covers:
1) /order-summary includes WA tax (10.25%)
2) /confirm-zelle-payment confirms order and returns totals
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import WA_TAX_RATE, SessionState, app, sessions

client = TestClient(app)


@pytest.fixture
def seeded_session_with_menu():
    sid = f"sess-{uuid4().hex}"
    state = SessionState()
    state.menu = [
        {"name": "Breakfast A", "type": "Breakfast", "price": 11.0},
        {"name": "Lunch A", "type": "Main Meal", "price": 15.0},
    ]
    sessions[sid] = state.model_dump()
    try:
        yield sid
    finally:
        sessions.pop(sid, None)


def test_order_summary_includes_wa_tax(seeded_session_with_menu):
    sid = seeded_session_with_menu

    response = client.post("/order-summary", json={"session_id": sid})
    assert response.status_code == 200

    payload = response.json()
    assert payload["ok"] is True
    assert payload["session_id"] == sid
    assert payload["items_count"] == 2

    expected_subtotal = 26.00  # 11 + 15
    expected_tax = round(expected_subtotal * WA_TAX_RATE, 2)
    expected_total = round(expected_subtotal + expected_tax, 2)

    assert payload["subtotal"] == expected_subtotal
    assert payload["tax"] == expected_tax
    assert payload["tax_rate"] == WA_TAX_RATE
    assert payload["total"] == expected_total


def test_confirm_zelle_payment_returns_confirmed(seeded_session_with_menu):
    sid = seeded_session_with_menu

    response = client.post(
        "/confirm-zelle-payment",
        json={
            "session_id": sid,
            "full_name": "Test Customer",
            "email": "test.customer@example.com",
            "payment_proof_url": "/uploads/payment_proofs/mock-proof.png",
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["ok"] is True
    assert "confirmed" in payload["message"].lower()
    assert "prepared" in payload["message"].lower()

    summary = payload["summary"]
    expected_subtotal = 26.00
    expected_tax = round(expected_subtotal * WA_TAX_RATE, 2)
    expected_total = round(expected_subtotal + expected_tax, 2)

    assert summary["subtotal"] == expected_subtotal
    assert summary["tax"] == expected_tax
    assert summary["tax_rate"] == WA_TAX_RATE
    assert summary["total"] == expected_total
