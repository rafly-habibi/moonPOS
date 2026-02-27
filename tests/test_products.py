def test_create_product(client):
    response = client.post("/products", json={
        "sku": "TEST-001",
        "name": "Test Product",
        "sell_price": "10000",
        "cost_price": "5000",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-001"
    assert data["name"] == "Test Product"
    assert data["is_active"] is True


def test_create_product_duplicate_sku(client):
    payload = {"sku": "DUP-001", "name": "Prod A", "sell_price": "10000", "cost_price": "5000"}
    client.post("/products", json=payload)
    response = client.post("/products", json=payload)
    assert response.status_code == 409


def test_list_products(client):
    client.post("/products", json={"sku": "P-001", "name": "A", "sell_price": "1000", "cost_price": "500"})
    client.post("/products", json={"sku": "P-002", "name": "B", "sell_price": "2000", "cost_price": "1000"})
    response = client.get("/products")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_products_low_stock_filter(client):
    client.post("/products", json={
        "sku": "LOW-001", "name": "Low Stock", "sell_price": "1000", "cost_price": "500",
        "stock_qty": 2, "min_stock": 10,
    })
    client.post("/products", json={
        "sku": "OK-001", "name": "Normal Stock", "sell_price": "1000", "cost_price": "500",
        "stock_qty": 100, "min_stock": 10,
    })
    response = client.get("/products?low_stock_only=true")
    assert response.status_code == 200
    skus = [p["sku"] for p in response.json()]
    assert "LOW-001" in skus
    assert "OK-001" not in skus
