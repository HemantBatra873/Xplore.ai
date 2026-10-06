"""
Task CRUD end-to-end tests (through the HTTP API).
"""


def _create_user_and_get_token(client, suffix: str) -> str:
    email = f"task-{suffix}@example.com"
    client.post(
        "/api/v1/users/",
        json={
            "username": f"task_{suffix}",
            "email": email,
            "password": "testpassword123",
            "full_name": f"Task User {suffix}",
        },
    )
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "testpassword123"},
    )
    return response.json()["access_token"]


class TestTaskCreate:
    def test_create_task_success(self, client):
        token = _create_user_and_get_token(client, "create")
        response = client.post(
            "/api/v1/tasks/",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "Learn Xplore.ai", "description": "Read the docs and try a demo"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Learn Xplore.ai"
        assert data["description"] == "Read the docs and try a demo"
        assert data["status"] == "pending"
        assert "id" in data
        assert "owner_id" in data

    def test_create_task_without_auth_fails(self, client):
        response = client.post(
            "/api/v1/tasks/",
            json={"title": "unauthorized task"},
        )
        assert response.status_code == 401

    def test_create_task_missing_title_fails(self, client):
        token = _create_user_and_get_token(client, "no-title")
        response = client.post(
            "/api/v1/tasks/",
            headers={"Authorization": f"Bearer {token}"},
            json={"description": "no title"},
        )
        assert response.status_code == 422


class TestTaskList:
    def test_list_tasks_returns_user_tasks(self, client):
        token = _create_user_and_get_token(client, "list")
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/api/v1/tasks/", headers=headers, json={"title": "Task A"})
        client.post("/api/v1/tasks/", headers=headers, json={"title": "Task B"})
        response = client.get("/api/v1/tasks/", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        titles = {item["title"] for item in data}
        assert titles == {"Task A", "Task B"}

    def test_list_tasks_user_isolation(self, client):
        token_a = _create_user_and_get_token(client, "isolate-a")
        token_b = _create_user_and_get_token(client, "isolate-b")
        client.post(
            "/api/v1/tasks/",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"title": "User A task"},
        )
        client.post(
            "/api/v1/tasks/",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"title": "User B task"},
        )
        resp_a = client.get("/api/v1/tasks/", headers={"Authorization": f"Bearer {token_a}"})
        resp_b = client.get("/api/v1/tasks/", headers={"Authorization": f"Bearer {token_b}"})
        assert len(resp_a.json()) == 1
        assert resp_a.json()[0]["title"] == "User A task"
        assert len(resp_b.json()) == 1
        assert resp_b.json()[0]["title"] == "User B task"

    def test_list_tasks_empty(self, client):
        token = _create_user_and_get_token(client, "empty")
        response = client.get("/api/v1/tasks/", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == []


class TestTaskGet:
    def test_get_task_by_id(self, client):
        token = _create_user_and_get_token(client, "get")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/v1/tasks/",
            headers=headers,
            json={"title": "Fetch test"},
        )
        task_id = created.json()["id"]
        response = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["title"] == "Fetch test"

    def test_get_task_not_found(self, client):
        token = _create_user_and_get_token(client, "nf")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/v1/tasks/99999", headers=headers)
        assert response.status_code == 404

    def test_get_task_other_user_forbidden(self, client):
        token_a = _create_user_and_get_token(client, "other-a")
        token_b = _create_user_and_get_token(client, "other-b")
        created = client.post(
            "/api/v1/tasks/",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"title": "Private task"},
        )
        task_id = created.json()["id"]
        response = client.get(
            f"/api/v1/tasks/{task_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert response.status_code == 404


class TestTaskUpdate:
    def test_update_task_title(self, client):
        token = _create_user_and_get_token(client, "upd-title")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/v1/tasks/", headers=headers, json={"title": "Original title"})
        task_id = created.json()["id"]
        response = client.put(
            f"/api/v1/tasks/{task_id}",
            headers=headers,
            json={"title": "New title"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "New title"

    def test_update_task_status(self, client):
        token = _create_user_and_get_token(client, "upd-status")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/v1/tasks/", headers=headers, json={"title": "Todo"})
        task_id = created.json()["id"]
        response = client.put(
            f"/api/v1/tasks/{task_id}",
            headers=headers,
            json={"status": "completed"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_update_task_partial(self, client):
        token = _create_user_and_get_token(client, "upd-partial")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/v1/tasks/",
            headers=headers,
            json={
                "title": "Partial update",
                "description": "Original description",
                "status": "pending",
            },
        )
        task_id = created.json()["id"]
        response = client.put(
            f"/api/v1/tasks/{task_id}",
            headers=headers,
            json={"description": "New description"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Partial update"
        assert data["description"] == "New description"
        assert data["status"] == "pending"


class TestTaskDelete:
    def test_delete_task(self, client):
        token = _create_user_and_get_token(client, "delete")
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/v1/tasks/", headers=headers, json={"title": "To delete"})
        task_id = created.json()["id"]
        response = client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["title"] == "To delete"
        get_resp = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
        assert get_resp.status_code == 404

    def test_delete_task_not_found(self, client):
        token = _create_user_and_get_token(client, "del-nf")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/v1/tasks/99999", headers=headers)
        assert response.status_code == 404
