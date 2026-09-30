"""Run the collection's requests against a fresh app; Postman itself isn't started."""
import json
from pathlib import Path
import re


def test_postman_collection_workflow(client):
    path = Path(__file__).resolve().parents[1] / "postman/Banking-App.postman_collection.json"
    collection = json.loads(path.read_text(encoding="utf-8"))
    # Postman's pre-request scripts generate these two; the replay uses fixed values instead.
    variables = {"baseUrl": "", "email": "collection@example.com", "idempotencyKey": "collection-deposit-1"}
    declared = {v["key"] for v in collection["variable"]}
    assert set(re.findall(r"\{\{(\w+)\}\}", path.read_text(encoding="utf-8"))) <= declared

    def substitute(value):
        return re.sub(r"\{\{(\w+)\}\}", lambda m: str(variables[m[1]]), value)

    for item in collection["item"]:
        request = item["request"]
        body = json.loads(substitute(request["body"]["raw"])) if "body" in request else None
        headers = {h["key"]: substitute(h["value"]) for h in request["header"]}
        response = client.request(request["method"], substitute(request["url"]), json=body, headers=headers)
        tests = next(e["script"]["exec"] for e in item["event"] if e["listen"] == "test")
        expected = int(re.search(r"status\((\d+)\)", tests[0])[1])
        assert response.status_code == expected, (item["name"], response.text)
        if expected == 204:
            assert response.content == b""
        data = response.json() if response.content else None
        name = item["name"]
        if name == "Create Customer":
            variables["customerId"] = data["customerId"]
            assert re.fullmatch(r"[0-9a-f]{24}", data["customerId"])
        elif name == "Edit Customer":
            assert data["name"] == "Moataz Hikal"
            assert data["email"] == "updated." + variables["email"]
        elif name == "Create Account":
            variables["accountId"] = data["accountId"]
        elif name == "Create Second Account":
            variables["secondAccountId"] = data["accountId"]
        elif name == "Get Customer Accounts":
            assert len(data) == 2
            assert all(a["customerId"] == variables["customerId"] for a in data)
        elif name in ("Deposit", "Retry Deposit (same Idempotency-Key)"):
            assert data["balance"] == "100.00"  # the retry replays the first result
        elif name == "Get Account":
            assert data["balance"] == "75.00"  # the retry did not deposit again
        elif name == "Transactions":
            assert [t["type"] for t in data] == ["DEPOSIT", "WITHDRAW"]
        elif name == "Search Customers":
            assert [(c["customerId"], c["totalBalance"], c["category"]) for c in data] == [
                (variables["customerId"], "75.00", "LOW")]
        elif name == "Get Alerts":
            assert [(a["type"], a["totalBalance"], a["threshold"]) for a in data] == [
                ("LOW_BALANCE", "75.00", "100.00")]
        elif name == "Audit First Page":
            assert [t["type"] for t in data["items"]] == ["DEPOSIT"]
            assert data["nextCursor"]
            variables["auditCursor"] = data["nextCursor"]
        elif name == "Audit Next Page":
            assert [t["type"] for t in data["items"]] == ["WITHDRAW"]
            assert data["nextCursor"] is None
        elif name == "Audit After Deletion":
            assert [t["type"] for t in data["items"]] == ["DEPOSIT", "WITHDRAW", "WITHDRAW"]
            assert {t["accountId"] for t in data["items"]} == {variables["accountId"]}
    names = [item["name"] for item in collection["item"]]
    for required in ("Retry Deposit (same Idempotency-Key)", "Search Customers", "Get Alerts", "Audit First Page",
                     "Audit Next Page", "Audit After Deletion"):
        assert required in names
