from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    plan: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class APIKeyCreate(BaseModel):
    name: str


class APIKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool

    model_config = {"from_attributes": True}


class APIKeyCreated(BaseModel):
    """Returned once on creation — includes the full key."""
    id: int
    name: str
    key_prefix: str
    full_key: str
    created_at: datetime


class UsageSummary(BaseModel):
    this_month: int
    monthly_limit: int
    total_all_time: int
    daily: list[dict]  # [{date, count}]


class UsageRecord(BaseModel):
    id: int
    action: str
    mutant_id: Optional[str]
    api_key_prefix: Optional[str]
    timestamp: datetime

    model_config = {"from_attributes": True}


class BillingPlan(BaseModel):
    name: str
    price: int  # USD/month, 0 = free
    fixes_per_month: int  # -1 = unlimited
    api_keys: int           # -1 = unlimited
    ai_generation: bool
    team_seats: int
    support: str
    features: list[str]


PLANS: dict[str, BillingPlan] = {
    "hobby": BillingPlan(
        name="Hobby",
        price=0,
        fixes_per_month=250,
        api_keys=1,
        ai_generation=False,
        team_seats=1,
        support="Community",
        features=[
            "250 mutation fixes / month",
            "1 API key",
            "Rule-based generation",
            "1 project",
            "Community support",
        ],
    ),
    "pro": BillingPlan(
        name="Pro",
        price=19,
        fixes_per_month=10_000,
        api_keys=5,
        ai_generation=True,
        team_seats=1,
        support="Email",
        features=[
            "10,000 mutation fixes / month",
            "5 API keys",
            "AI-powered generation (Claude & GPT-4)",
            "Unlimited projects",
            "Usage analytics",
            "Email support",
        ],
    ),
    "team": BillingPlan(
        name="Team",
        price=79,
        fixes_per_month=-1,
        api_keys=-1,
        ai_generation=True,
        team_seats=10,
        support="Priority",
        features=[
            "Unlimited mutation fixes",
            "Unlimited API keys",
            "AI-powered generation",
            "10 team seats",
            "SSO / SAML",
            "Priority support + SLA",
            "Audit logs",
        ],
    ),
}
