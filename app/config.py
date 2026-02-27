import os

DATABASE_URL: str = os.getenv("MOONPOS_DB_URL", "sqlite:///./moonpos.db")

_cors_raw = os.getenv("MOONPOS_CORS_ORIGINS", "*").strip()
CORS_ORIGINS: list[str] = (
    ["*"]
    if _cors_raw == "*"
    else [o.strip() for o in _cors_raw.split(",") if o.strip()]
)
