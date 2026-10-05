def test_login_success(client):
    """
    Test successful login returns a token.
    Creates a user in this file because pytest file order is not guaranteed.
    """
    # 1. Create a user
    client.post(
        "/api/v1/users/",
        json={"username": "authuser", "email": "auth@example.com", "password": "authpassword"},
    )

    # 2. Login
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "auth@example.com", "password": "authpassword"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client):
    """
    Test login with wrong password.
    """
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "auth@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == 1005


def test_access_protected_route_without_token(client):
    """
    Test protected route without token.
    """
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
