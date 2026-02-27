import pytest


@pytest.fixture
def product_id(client):
    r = client.post("/products", json={
        "sku": "PROD-INV",
        "name": "Inventory Product",
        "sell_price": "15000",
        "cost_price": "6000",
        "stock_qty": 30,
        "min_stock": 5,
    })
    return r.json()["id"]


def test_adjust_inventory_restock(client, product_id):
    response = client.post("/inventory/adjust", json={
        "product_id": product_id,
        "quantity_change": 20,
        "reason": "Restock dari supplier",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["after_qty"] == 50
    assert data["movement_type"] == "restock"


def test_adjust_inventory_reduction(client, product_id):
    response = client.post("/inventory/adjust", json={
        "product_id": product_id,
        "quantity_change": -10,
        "reason": "Koreksi stok",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["after_qty"] == 20
    assert data["movement_type"] == "adjustment"


def test_adjust_inventory_below_zero(client, product_id):
    response = client.post("/inventory/adjust", json={
        "product_id": product_id,
        "quantity_change": -999,
    })
    assert response.status_code == 400


def test_adjust_zero_quantity_rejected(client, product_id):
    response = client.post("/inventory/adjust", json={
        "product_id": product_id,
        "quantity_change": 0,
    })
    assert response.status_code == 422


def test_low_stock_alert(client, product_id):
    # Kurangi stok ke bawah min_stock (5)
    client.post("/inventory/adjust", json={
        "product_id": product_id,
        "quantity_change": -27,  # 30 - 27 = 3, di bawah min_stock=5
    })
    response = client.get("/inventory/low-stock")
    assert response.status_code == 200
    ids = [p["id"] for p in response.json()]
    assert product_id in ids


def test_movements_recorded(client, product_id):
    client.post("/inventory/adjust", json={
        "product_id": product_id,
        "quantity_change": 10,
    })
    response = client.get("/inventory/movements")
    assert response.status_code == 200
    product_ids = [m["product_id"] for m in response.json()]
    assert product_id in product_ids
