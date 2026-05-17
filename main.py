import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from routers import auth, api_keys, usage, billing, blog
import auth as auth_utils
import schemas
from config import CORS_ORIGINS

logger = logging.getLogger("quell")

_DB_READY = False


def _init_db(retries: int = 5, delay: float = 3.0) -> bool:
    """Create tables and run migrations. Retries on transient DB errors."""
    global _DB_READY
    _migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR DEFAULT 'email'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR",
    ]
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            with engine.connect() as conn:
                for stmt in _migrations:
                    conn.execute(text(stmt))
                conn.commit()
            _DB_READY = True
            logger.info("Database ready.")
            return True
        except Exception as exc:
            logger.error("DB init attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(delay)
    logger.error("All DB init attempts failed — app running in degraded mode.")
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    yield


app = FastAPI(title="Quell API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(api_keys.router, prefix="/api/keys", tags=["api-keys"])
app.include_router(usage.router, prefix="/api/usage", tags=["usage"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(blog.router, prefix="/api/blog/views", tags=["blog"])


@app.get("/")
def root():
    return {"status": "ok", "service": "Quell API"}


@app.get("/health")
def health():
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    status = "ok" if db_ok else "degraded"
    return {"status": status, "db": "ok" if db_ok else "unavailable"}


@app.get("/api/me", response_model=schemas.UserResponse)
def api_me(current_user=Depends(auth_utils.get_current_user)):
    """Alias used by the Quell CLI to verify the active token."""
    return current_user
