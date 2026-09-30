"""Run the collection's requests against a fresh app; Postman itself isn't started."""
import json
from pathlib import Path
import re

from fastapi.testclient import TestClient

import pytest

pytestmark = pytest.mark.integration


def test_postman_collection_workflow(client):
    path = Path(__file__).resolve().parents[1] / "postman/Banking-App.postman_collection.json"
    collection = json.loads(path.read_text(encoding="utf-8"))
    variables = {"baseUrl": "", "email": "collection@example.com"}

    def substitute(value):
        return re.sub(r"\{\{(\w+)\}\}", lambda m: str(variables[m[1]]), value)

    for item in collection["item"]:
        request = item["request"]
        body = json.loads(substitute(request["body"]["raw"])) if "body" in request else None
        response = client.request(request["method"], substitute(request["url"]), json=body)
        tests = next(e["script"]["exec"] for e in item["event"] if e["listen"] == "test")
        expected = int(re.search(r"status\((\d+)\)", tests[0])[1])
        assert response.status_code == expected, (item["name"], response.text)
        if expected == 204:
            assert response.content == b""
        if item["name"] == "Create Customer":
            variables["customerId"] = response.json()["customerId"]
        elif item["name"] == "Edit Customer":
            assert response.json()["name"] == "Moataz Hikal"
            assert response.json()["email"] == "updated." + variables["email"]
        elif item["name"] == "Create Account":
            variables["accountId"] = response.json()["accountId"]
        elif item["name"] == "Create Second Account":
            variables["secondAccountId"] = response.json()["accountId"]
        elif item["name"] == "Get Customer Accounts":
            assert len(response.json()) == 2
            assert all(a["customerId"] == variables["customerId"] for a in response.json())
        elif item["name"] == "Get Account":
            assert response.json()["balance"] == "75.00"
        elif item["name"] == "Transactions":
            variables["transactionId"] = response.json()[0]["txnId"]
            assert [t["type"] for t in response.json()] == ["DEPOSIT", "WITHDRAW"]
        elif item["name"] in {"Initial Notifications", "Premium Notifications", "Low Balance Alerts", "Marketing History", "Audit After Closure"}:
            expected_counts = {"Initial Notifications":2,"Premium Notifications":1,"Low Balance Alerts":3,"Marketing History":2,"Audit After Closure":5}
            assert len(response.json()) == expected_counts[item["name"]]
        elif item["name"] == "Premium Customer Search":
            assert response.json()[0]['totalBalance'] == '10000.00'
