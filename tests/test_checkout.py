import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
CASES = json.loads((Path(__file__).parents[2] / "shared" / "checkout-cases.json").read_text())

DINE = {"name": "Asha Rao", "phone": "9876543210", "email": "asha@example.com", "orderType": "dine-in", "table": 5, "tip": 10, "acceptTerms": True}
DELIVERY = {"name": "Asha Rao", "phone": "9876543210", "email": "asha@example.com", "orderType": "delivery", "street": "12 Lake View Road", "pincode": "500081", "tip": 0, "acceptTerms": True}


# ---- the shared cases: the browser and the server must agree ----

@pytest.mark.parametrize("case", CASES["valid"], ids=lambda c: c["name"])
def test_server_accepts_every_valid_shared_case(case):
    r = client.post("/api/checkout", json=case["payload"])
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("case", CASES["invalid"], ids=lambda c: c["name"])
def test_server_rejects_every_invalid_shared_case_for_the_same_fields(case):
    r = client.post("/api/checkout", json=case["payload"])
    assert r.status_code == 422, r.text
    assert sorted(r.json()["errors"]) == case["errors"]


# ---- what the server does on its own ----

def test_dine_in_answer_has_a_table_and_no_address():
    body = client.post("/api/checkout", json=DINE).json()
    assert body["table"] == 5 and "street" not in body and "pincode" not in body


def test_delivery_answer_has_an_address_and_no_table():
    body = client.post("/api/checkout", json=DELIVERY).json()
    assert body["street"] == "12 Lake View Road" and body["pincode"] == "500081" and "table" not in body


def test_the_server_trims_text_itself():
    body = client.post("/api/checkout", json={**DINE, "name": "  Asha Rao  "}).json()
    assert body["name"] == "Asha Rao"


def test_a_table_sent_with_a_delivery_order_is_ignored():
    body = client.post("/api/checkout", json={**DELIVERY, "table": 99}).json()
    assert "table" not in body


def test_order_ids_go_up():
    a = client.post("/api/checkout", json=DINE).json()["orderId"]
    b = client.post("/api/checkout", json=DINE).json()["orderId"]
    assert b == a + 1


def test_a_rejected_order_does_not_use_up_an_id():
    a = client.post("/api/checkout", json=DINE).json()["orderId"]
    client.post("/api/checkout", json={**DINE, "table": 0})
    b = client.post("/api/checkout", json=DINE).json()["orderId"]
    assert b == a + 1


def test_error_shape_is_detail_plus_errors_by_field():
    r = client.post("/api/checkout", json={**DINE, "phone": "1"})
    assert r.json()["detail"] == "Please fix the highlighted fields."
    assert "phone" in r.json()["errors"]
    assert "Value error" not in r.json()["errors"]["phone"]


def test_a_body_that_is_not_json_is_a_422_not_a_crash():
    r = client.post("/api/checkout", content="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_an_empty_body_is_a_422():
    assert client.post("/api/checkout", json={}).status_code == 422


def test_true_is_not_accepted_as_a_table_number():
    # In Python True == 1, so a careless check would accept this.
    assert client.post("/api/checkout", json={**DINE, "table": True}).status_code == 422


def test_true_is_not_accepted_as_a_tip():
    assert client.post("/api/checkout", json={**DINE, "tip": True}).status_code == 422


def test_non_ascii_digits_are_not_a_phone_number():
    # A leading ASCII 9 followed by 9 Arabic-Indic digits: it only fails if the rule is [0-9], not \d.
    assert client.post("/api/checkout", json={**DINE, "phone": "9" + "٨٧٦٥٤٣٢١٠"}).status_code == 422


def test_cors_allows_the_dev_page():
    r = client.options("/api/checkout", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_does_not_allow_other_sites():
    r = client.options("/api/checkout", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
