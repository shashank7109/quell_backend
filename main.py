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


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # In-place migrations — idempotent
    _migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR DEFAULT 'email'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR",
    ]
    with engine.connect() as conn:
        for stmt in _migrations:
            conn.execute(text(stmt))
        conn.commit()
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


@app.get("/api/me", response_model=schemas.UserResponse)
def api_me(current_user=Depends(auth_utils.get_current_user)):
    """Alias used by the Quell CLI to verify the active token."""
    return current_user
