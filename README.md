# Quell Backend

FastAPI backend for the Quell web dashboard. Handles authentication, API key management, usage tracking, and billing via Razorpay.

## Stack

- **FastAPI** — REST API framework
- **SQLAlchemy 2** — ORM with PostgreSQL
- **psycopg2** — PostgreSQL driver
- **passlib + bcrypt** — password hashing
- **python-jose** — JWT tokens
- **Razorpay** — payment processing (INR)
- **httpx** — Google OAuth token exchange
- **Pydantic v2** — request/response validation

## Project structure

```
backend/
├── main.py           # App entry point, CORS, startup migrations
├── config.py         # Environment variable loading (pydantic-settings)
├── database.py       # SQLAlchemy engine + session factory
├── models.py         # ORM models (User, APIKey, UsageRecord)
├── schemas.py        # Pydantic request/response schemas
├── auth.py           # JWT helpers, password hashing, current-user dep
└── routers/
    ├── auth.py       # /api/auth — register, login, Google OAuth callback
    ├── api_keys.py   # /api/keys — create, list, revoke API keys
    ├── usage.py      # /api/usage — summary, daily chart, request history
    └── billing.py    # /api/billing — plans, Razorpay order + verify, upgrade
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account (email + password) |
| POST | `/api/auth/login` | Sign in, returns JWT |
| POST | `/api/auth/google-callback` | Exchange Google OAuth code for JWT |
| GET | `/api/keys` | List API keys |
| POST | `/api/keys` | Create API key |
| DELETE | `/api/keys/{id}` | Revoke API key |
| GET | `/api/usage/summary` | Monthly quota + daily chart data |
| GET | `/api/usage/history` | Paginated request history |
| GET | `/api/billing/current` | Current plan + details |
| GET | `/api/billing/plans` | All available plans |
| POST | `/api/billing/create-order` | Create Razorpay order |
| POST | `/api/billing/verify-payment` | Verify Razorpay HMAC signature |
| POST | `/api/billing/upgrade` | Direct plan change (downgrade / dev) |

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ (or use the Docker Compose file in `web/`)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### 1. Install dependencies

```bash
uv pip install -r requirements.txt
# or
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

Required variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | Long random string for JWT signing |
| `RAZORPAY_KEY_ID` | Razorpay API key ID |
| `RAZORPAY_KEY_SECRET` | Razorpay API key secret |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |

### 3. Start PostgreSQL (Docker)

```bash
# From the web/ directory
docker compose up -d
```

### 4. Run the server

```bash
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

## Database

Tables are created automatically on startup via SQLAlchemy's `create_all`. Schema migrations for new columns use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in the startup event handler in `main.py`.

## Authentication

All protected routes require a `Bearer` token in the `Authorization` header:

```
Authorization: Bearer <jwt_token>
```

Tokens are issued at login/register and expire after 7 days.

## Payments

Payments go through Razorpay. Prices are in INR:

| Plan | Price |
|------|-------|
| Hobby | Free |
| Pro | ₹1,599 / month |
| Team | ₹6,599 / month |

Payment flow: `create-order` → Razorpay checkout modal (frontend) → `verify-payment` (HMAC signature check) → plan upgraded in DB.

## License

MIT
