# moonPOS (Cloud-Ready)

POS cloud-ready untuk:
- checkout order
- monitor stok
- pembukuan (double-entry sederhana)
- analisa data penjualan
- dashboard frontend (HTML/CSS/JS)

Tech stack:
- FastAPI
- SQLAlchemy
- SQLite (lokal) / PostgreSQL (cloud)

## 1) Jalankan Lokal

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs:
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

Dashboard web:
- `http://127.0.0.1:8000/web`

Database default lokal:
- `sqlite:///./moonpos.db`

## 2) Konfigurasi Cloud

Atur environment variable:
- `MOONPOS_DB_URL`  
  contoh PostgreSQL:
  `postgresql+psycopg://username:password@host:5432/moonpos`
- `MOONPOS_CORS_ORIGINS`  
  contoh:
  `https://your-frontend-domain.com,http://localhost:3000`

Lihat template di file `.env.example`.

## 3) Deploy Pakai Docker

```bash
docker build -t moonpos .
docker run -p 8000:8000 --env-file .env moonpos
```

### Opsi yang lebih praktis: Docker Compose (App + PostgreSQL)

```bash
docker compose up -d --build
```

Akses:
- Dashboard: `http://127.0.0.1:8000/web`
- API docs: `http://127.0.0.1:8000/docs`

Stop:
```bash
docker compose down
```

Stop + hapus data database:
```bash
docker compose down -v
```

### Supaya mudah dibawa ke device lain

Export image:
```bash
docker save moonpos-api -o moonpos-api.tar
```

Import image di device lain:
```bash
docker load -i moonpos-api.tar
```

## 4) Endpoint Utama

Frontend:
- `GET /web`
- `GET /static/*`

Produk & stok:
- `POST /products`
- `GET /products`
- `GET /inventory/low-stock`
- `POST /inventory/adjust`
- `GET /inventory/movements`

Order:
- `POST /checkout`
- `GET /orders`

Pembukuan:
- `GET /bookkeeping/ledger`
- `GET /bookkeeping/trial-balance`

Analitik:
- `GET /analytics/sales-summary`
- `GET /analytics/top-products`
- `GET /analytics/stock-valuation`

Healthcheck:
- `GET /health`

## 5) Contoh Request Checkout

```json
POST /checkout
{
  "items": [
    { "product_id": 1, "quantity": 2 },
    { "product_id": 2, "quantity": 1 }
  ],
  "discount": 2000,
  "tax": 1000,
  "payment_method": "cash"
}
```

## 6) Test Cepat Dari Web

1. Buka `http://127.0.0.1:8000/web`
2. Di tab `Checkout`, tambah item ke keranjang lalu klik `Proses Checkout`
3. Pindah ke tab `Stok`, cek stok produk berkurang dan movement tercatat
4. Pindah ke tab `Pembukuan`, cek ledger + trial balance ikut update
5. Pindah ke tab `Analitik`, cek revenue/profit/top produk update

## 7) Catatan

- Saat startup pertama, sistem otomatis seed 3 produk contoh.
- Checkout akan otomatis:
  - mengurangi stok
  - mencatat movement stok
  - membuat jurnal pembukuan:
    - Dr Cash / Cr Sales Revenue
    - Dr COGS / Cr Inventory
