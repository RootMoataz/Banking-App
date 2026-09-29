"""Check customer and account edits, ownership, and deletion order."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def customer(client, email="moataz@example.com", name="Moataz Hikal"):
    response = client.post("/api/customers", json={"name": name, "email": email})
    assert response.status_code == 201
    return response.json()


def account(client, customer_id):
    response = client.post("/api/accounts", json={"customerId": customer_id, "accountType": "SAVINGS"})
    assert response.status_code == 201
    return response.json()


def test_customer_crud(client):
    assert client.get("/api/customers").json() == []
    original = customer(client, name="Moataz Hikal".upper())
    url = f"/api/customers/{original['customerId']}"
    assert client.get(url).json() == original
    assert client.get("/api/customers").json() == [original]
    edited = client.put(url, json={"name": "Moataz Hikal", "email": "moataz.updated@example.com"})
    assert edited.status_code == 200
    assert edited.json()["name"] == "Moataz Hikal"
    assert edited.json()["createdAt"] == original["createdAt"]
    assert edited.json()["customerId"] == original["customerId"]
    assert client.get(url).json() == edited.json()
    deleted = client.delete(url)
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(url).status_code == 404
    assert client.get("/api/customers").json() == []
    assert customer(client, "moataz.updated@example.com")["customerId"] > original["customerId"]


def test_one_customer_many_accounts_and_name_edit(client):
    first = customer(client, name="Moataz Hikal".upper())["customerId"]
    second = customer(client, "second@example.com")["customerId"]
    accounts = [account(client, first), account(client, first)]
    assert all(a["customerId"] == first and a["userId"] == first for a in accounts)
    assert client.get(f"/api/customers/{first}/accounts").json() == accounts
    assert client.get(f"/api/customers/{second}/accounts").json() == []
    assert client.get("/api/accounts").json() == accounts
    assert client.delete(f"/api/customers/{first}").status_code == 409
    client.put(f"/api/customers/{first}", json={"name": "Moataz Hikal", "email": "moataz@example.com"})
    assert all(a["userName"] == "Moataz Hikal" for a in client.get(f"/api/customers/{first}/accounts").json())


def test_account_crud_and_deletion_rules(client):
    id = customer(client)["customerId"]
    original = account(client, id)
    url = f"/api/accounts/{original['accountId']}"
    edited = client.put(url, json={"accountType": "CURRENT"})
    assert edited.status_code == 200
    assert edited.json()["accountType"] == "CURRENT"
    for key in ["customerId", "userId", "accountId", "createdAt", "balance"]:
        assert edited.json()[key] == original[key]
    client.post(url + "/deposit", json={"amount": "1.23"})
    assert client.delete(url).status_code == 409
    assert client.get(url).json()["balance"] == "1.23"
    client.post(url + "/withdraw", json={"amount": "1.23"})
    deleted = client.delete(url)
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(url).status_code == 404
    assert client.get(url + "/transactions").status_code == 404
    assert client.get(f"/api/customers/{id}/accounts").json() == []
    assert client.delete(f"/api/customers/{id}").status_code == 204


def test_deleted_ids_never_overwrite_survivors(client):
    # Deleting an early record must not make the next ID collide with a later one.
    customers = [customer(client, f"person{i}@example.com") for i in range(3)]
    client.delete(f"/api/customers/{customers[0]['customerId']}")
    assert customer(client, "new@example.com")["customerId"] == 4
    assert client.get("/api/customers/3").json() == customers[2]
    accounts = [account(client, 3) for _ in range(3)]
    client.delete(f"/api/accounts/{accounts[0]['accountId']}")
    assert account(client, 3)["accountId"] == 4
    assert client.get("/api/accounts/3").json() == accounts[2]


def test_edit_email_uniqueness_and_index_cleanup(client):
    customer(client)
    customer(client, "second@example.com")
    response = client.put("/api/customers/2", json={"name": "Moataz Hikal", "email": "MOATAZ@example.com"})
    assert response.status_code == 409
    assert client.get("/api/customers/2").json()["email"] == "second@example.com"
    assert client.put("/api/customers/1", json={"name": "Moataz Hikal", "email": "MOATAZ@example.com"}).status_code == 200
    assert client.put("/api/customers/1", json={"name": "Moataz Hikal", "email": "new@example.com"}).status_code == 200
    assert customer(client)["customerId"] == 3


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/customers/999", None),
    ("GET", "/api/customers/999/accounts", None),
    ("PUT", "/api/customers/999", {"name": "Moataz Hikal", "email": "none@example.com"}),
    ("DELETE", "/api/customers/999", None),
    ("PUT", "/api/accounts/999", {"accountType": "CURRENT"}),
    ("DELETE", "/api/accounts/999", None),
])
def test_crud_missing_resources(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 404


@pytest.mark.parametrize("body", [{}, {"name": "Moataz Hikal"}, {"name": " ", "email": "moataz@example.com"},
                                      {"name": "Moataz Hikal", "email": "invalid"},
                                      {"name": "Moataz Hikal", "email": "moataz@example.com", "customerId": 9}])
def test_customer_edit_validation(client, body):
    original = customer(client)
    assert client.put("/api/customers/1", json=body).status_code == 422
    assert client.get("/api/customers/1").json() == original


@pytest.mark.parametrize("body", [{}, {"accountType": " "}, {"accountType": "x" * 51},
    {"accountType": "CURRENT", "balance": 999}, {"accountType": "CURRENT", "customerId": 2}])
def test_account_edit_rejects_invalid_fields(client, body):
    original = account(client, customer(client)["customerId"])
    assert client.put("/api/accounts/1", json=body).status_code == 422
    assert client.get("/api/accounts/1").json() == original


def test_legacy_users_share_customer_records(client):
    user = client.post("/api/users", json={"name": "Moataz Hikal", "email": "legacy@example.com"}).json()
    assert client.get(f"/api/customers/{user['userId']}").json()["name"] == "Moataz Hikal"
    assert client.post("/api/customers", json={"name": "Moataz Hikal", "email": "legacy@example.com"}).status_code == 409


def test_swagger_documents_crud_and_customer_ownership(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert set(paths["/api/customers"]) == {"get", "post"}
    assert set(paths["/api/customers/{id}"]) == {"get", "put", "delete"}
    assert set(paths["/api/accounts"]) == {"get", "post"}
    assert set(paths["/api/accounts/{id}"]) == {"get", "put", "delete"}
    assert "204" in paths["/api/customers/{id}"]["delete"]["responses"]
    assert "409" in paths["/api/accounts/{id}"]["delete"]["responses"]
    assert "customerId" in schema["components"]["schemas"]["AccountCreate"]["properties"]
    assert client.get("/docs").status_code == 200
