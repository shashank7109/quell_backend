import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://quell:quell@localhost:5432/quell",
)

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-use-a-long-random-string")

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

# Deployment URLs
# FRONTEND_URL: your Vercel deployment URL (no trailing slash)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# CORS_ORIGINS: comma-separated list of allowed origins
# e.g. "https://quell.vercel.app,http://localhost:3000"
_cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
CORS_ORIGINS: list[str] = [o.strip() for o in _cors_raw.split(",") if o.strip()]
