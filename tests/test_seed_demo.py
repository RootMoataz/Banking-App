import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "seed_demo.py"
spec = importlib.util.spec_from_file_location("seed_demo", SCRIPT)
seed_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_demo)

EXPECTED = {  # email -> (category, number of accounts)
    "demo-low@example.com": ("LOW", 2),
    "demo-standard@example.com": ("STANDARD", 2),
    "demo-premium@example.com": ("PREMIUM", 2),
}


def counts(db):
    return {name: db[name].count_documents({}) for name in ("users", "customers", "accounts", "transactions",
                                                            "notifications")}


def login(anonymous_client, email, password=seed_demo.DEMO_PASSWORD):
    response = anonymous_client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    return body["user"], {"Authorization": f"Bearer {body['token']}"}


@pytest.fixture
def seeded(client, db, settings):
    # `client` signs in with its own test admin; that user is not a demo user and must survive every seed run.
    seed_demo.seed(db, settings)
    return client


def test_demo_accounts_have_the_documented_roles_and_categories(seeded, anonymous_client):
    user, admin = login(anonymous_client, "demo-admin@example.com")
    assert user["role"] == "ADMIN"
    customers = anonymous_client.get("/api/customers", headers=admin)
    assert customers.status_code == 200
    assert {c["email"] for c in customers.json()} == set(EXPECTED)
    found = {s["email"]: s["category"] for s in anonymous_client.get("/api/customers/search", headers=admin).json()}
    assert found == {email: category for email, (category, _) in EXPECTED.items()}
    premium = anonymous_client.get("/api/accounts/premium", headers=admin).json()
    assert [a["userName"] for a in premium] == ["Demo Premium"]

    for email, (category, account_count) in EXPECTED.items():
        user, headers = login(anonymous_client, email)
        assert user["role"] == "CUSTOMER"
        assert anonymous_client.get("/api/customers", headers=headers).status_code == 403
        accounts = anonymous_client.get(f"/api/customers/{user['customerId']}/accounts", headers=headers).json()
        assert len(accounts) == account_count
        assert {a["userId"] for a in accounts} == {user["customerId"]}
        for account in accounts:
            history = anonymous_client.get(f"/api/accounts/{account['accountId']}/transactions", headers=headers)
            assert history.status_code == 200 and history.json()
        assert sum(float(a["balance"]) for a in accounts) > 0


def test_marketing_customer_has_marketing_messages_and_the_others_do_not(seeded, anonymous_client):
    kinds = {}
    for email in EXPECTED:
        user, headers = login(anonymous_client, email)
        response = anonymous_client.get(f"/api/customers/{user['customerId']}/notifications", headers=headers)
        kinds[email] = {n["kind"] for n in response.json()}
    assert "PREMIUM_MARKETING" in kinds["demo-premium@example.com"]
    assert "LOW_BALANCE_ALERT" in kinds["demo-low@example.com"]
    assert not any("MARKETING" in k for k in kinds["demo-low@example.com"] | kinds["demo-standard@example.com"])


def test_running_the_seed_again_changes_nothing_and_reset_restores_it(seeded, db, settings, anonymous_client):
    before = counts(db)
    assert seed_demo.seed(db, settings) == {"removed": 0, "created": 0}
    assert counts(db) == before

    # A visitor with the demo admin deletes a demo customer; --reset brings everything back.
    _, admin = login(anonymous_client, "demo-admin@example.com")
    victim = db.customers.find_one({"emailKey": "demo-premium@example.com"})["_id"]
    assert anonymous_client.delete(f"/api/customers/{victim}", headers=admin).status_code == 204
    assert counts(db)["customers"] == before["customers"] - 1

    result = seed_demo.seed(db, settings, reset_first=True)
    assert result == {"removed": 3, "created": 4}  # the deleted customer's login went with it
    after = counts(db)
    # The app keeps a deleted customer's history and messages for audit, so those are not compared.
    assert {k: after[k] for k in ("users", "customers", "accounts")} == \
        {k: before[k] for k in ("users", "customers", "accounts")}
    login(anonymous_client, "demo-premium@example.com")


def test_reset_leaves_other_users_alone(seeded, db, settings, make_customer_client):
    other = make_customer_client("someone-else@example.com", "Someone Else")
    seed_demo.seed(db, settings, reset_first=True)
    assert db.customers.count_documents({"emailKey": "someone-else@example.com"}) == 1
    assert db.users.count_documents({"emailKey": "someone-else@example.com"}) == 1
    assert other.get(f"/api/customers/{other.customer_id}").status_code == 200
