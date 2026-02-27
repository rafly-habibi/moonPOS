from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import CORS_ORIGINS
from .db import Base, SessionLocal, engine
from .routers import analytics, bookkeeping, inventory, orders, products
from .services.seeder import seed_products

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="moonPOS API",
    version="0.1.0",
    description="POS cloud-ready API untuk checkout, stok, pembukuan, dan analitik.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(orders.router)
app.include_router(bookkeeping.router)
app.include_router(analytics.router)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_products(db)


@app.get("/")
def root() -> dict[str, object]:
    return {"service": "moonPOS API", "status": "ok", "cloud_ready": True}


@app.get("/web", include_in_schema=False)
def web_ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}
