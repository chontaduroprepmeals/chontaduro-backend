"""
Integration tests for POST /login endpoint.
Covers:
1) successful login
2) invalid credentials (401)
3) temporary lockout after failed attempts (429)
4) non-existent email returns 401
5) expired lockout allows login again
"""

import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import (
    LOGIN_ATTEMPTS,
    MAX_FAILED_LOGIN_ATTEMPTS,
    SessionLocal,
    User,
    app,
)

client = TestClient(app)


def _create_user(email: str, password: str, name: str = "Integration User") -> None:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            db.delete(existing)
            db.commit()

        user = User(
            name=name,
            email=email,
            hashed_password=User.hash_password(password),
        )
        db.add(user)
        db.commit()
    finally:
        db.close()


def _delete_user(email: str) -> None:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            db.delete(existing)
            db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean_login_attempts():
    LOGIN_ATTEMPTS.clear()
    yield
    LOGIN_ATTEMPTS.clear()


def test_login_success_returns_200():
    email = f"login-success-{uuid4().hex}@example.com"
    password = "StrongPass123!"
    _create_user(email=email, password=password)

    try:
        response = client.post("/login", json={"email": email, "password": password})
        assert response.status_code == 200

        payload = response.json()
        assert payload["message"] == "Login successful"
        assert payload["user"]["email"] == email
        assert "id" in payload["user"]
    finally:
        _delete_user(email)


def test_login_invalid_password_returns_401():
    email = f"login-unauthorized-{uuid4().hex}@example.com"
    password = "StrongPass123!"
    _create_user(email=email, password=password)

    try:
        response = client.post("/login", json={"email": email, "password": "WrongPass999!"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials."
    finally:
        _delete_user(email)


def test_login_lockout_after_failed_attempts_returns_429():
    email = f"login-lockout-{uuid4().hex}@example.com"
    password = "StrongPass123!"
    _create_user(email=email, password=password)

    try:
        for _ in range(MAX_FAILED_LOGIN_ATTEMPTS - 1):
            response = client.post("/login", json={"email": email, "password": "WrongPass999!"})
            assert response.status_code == 401

        lockout_response = client.post("/login", json={"email": email, "password": "WrongPass999!"})
        assert lockout_response.status_code == 429
        assert "Too many failed login attempts" in lockout_response.json()["detail"]

        while_locked_response = client.post("/login", json={"email": email, "password": password})
        assert while_locked_response.status_code == 429
    finally:
        _delete_user(email)


def test_login_non_existent_email_returns_401():
    email = f"login-missing-{uuid4().hex}@example.com"
    response = client.post("/login", json={"email": email, "password": "AnyPass123!"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials."


def test_login_after_lockout_expired_returns_200():
    email = f"login-expired-lockout-{uuid4().hex}@example.com"
    password = "StrongPass123!"
    _create_user(email=email, password=password)

    try:
        LOGIN_ATTEMPTS[email] = {
            "failed_attempts": 0,
            "lockout_until": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1),
        }

        response = client.post("/login", json={"email": email, "password": password})
        assert response.status_code == 200
        assert response.json()["message"] == "Login successful"
        assert email not in LOGIN_ATTEMPTS
    finally:
        _delete_user(email)
