import pytest


@pytest.fixture
def product_id(client):
    r = client.post("/products", json={
        "sku": "PROD-CHK",
        "name": "Checkout Product",
        "sell_price": "25000",
        "cost_price": "10000",
        "stock_qty": 50,
    })
    return r.json()["id"]


def test_checkout_success(client, product_id):
    response = client.post("/checkout", json={
        "items": [{"product_id": product_id, "quantity": 2}],
        "payment_method": "cash",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["total"] == "50000.00"
    assert data["cogs"] == "20000.00"
    assert data["gross_profit"] == "30000.00"


def test_checkout_reduces_stock(client, product_id):
    client.post("/checkout", json={
        "items": [{"product_id": product_id, "quantity": 3}],
        "payment_method": "cash",
    })
    products = client.get("/products").json()
    product = next(p for p in products if p["id"] == product_id)
    assert product["stock_qty"] == 47


def test_checkout_insufficient_stock(client, product_id):
    response = client.post("/checkout", json={
        "items": [{"product_id": product_id, "quantity": 999}],
        "payment_method": "cash",
    })
    assert response.status_code == 400


def test_checkout_with_discount_and_tax(client, product_id):
    response = client.post("/checkout", json={
        "items": [{"product_id": product_id, "quantity": 1}],
        "discount": "5000",
        "tax": "2500",
        "payment_method": "cash",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["total"] == "22500.00"  # 25000 - 5000 + 2500


def test_checkout_creates_ledger_entries(client, product_id):
    client.post("/checkout", json={
        "items": [{"product_id": product_id, "quantity": 1}],
        "payment_method": "cash",
    })
    ledger = client.get("/bookkeeping/ledger").json()
    accounts = [e["account"] for e in ledger]
    assert "Cash" in accounts
    assert "Sales Revenue" in accounts
    assert "COGS" in accounts
    assert "Inventory" in accounts


def test_checkout_credit_payment(client, product_id):
    response = client.post("/checkout", json={
        "items": [{"product_id": product_id, "quantity": 1}],
        "payment_method": "credit",
    })
    assert response.status_code == 201
    ledger = client.get("/bookkeeping/ledger").json()
    accounts = [e["account"] for e in ledger]
    assert "Accounts Receivable" in accounts
