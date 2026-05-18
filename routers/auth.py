import hashlib
import secrets
import base64
import logging
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth as auth_utils
import models
import schemas
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from database import get_db
from email_service import send_verification_email, send_password_reset_email

logger = logging.getLogger("quell.auth")

router = APIRouter()

TOKEN_EXPIRY_VERIFY = timedelta(hours=24)
TOKEN_EXPIRY_RESET = timedelta(hours=1)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Store hash; send raw to user."""
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def _set_token(user: models.User, purpose: str, expires_in: timedelta, db: Session) -> str:
    raw, hashed = _make_token()
    user.email_token = hashed
    user.email_token_purpose = purpose
    user.email_token_expires_at = datetime.utcnow() + expires_in
    db.commit()
    return raw


def _verify_token(token: str, purpose: str, db: Session) -> models.User:
    hashed = hashlib.sha256(token.encode()).hexdigest()
    user = db.query(models.User).filter(models.User.email_token == hashed).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if user.email_token_purpose != purpose:
        raise HTTPException(status_code=400, detail="Invalid token type")
    if user.email_token_expires_at and user.email_token_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token has expired")
    return user


def _clear_token(user: models.User, db: Session) -> None:
    user.email_token = None
    user.email_token_purpose = None
    user.email_token_expires_at = None
    db.commit()


# ── email/password register ───────────────────────────────────────────────────

@router.post("/register")
def register(body: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        email=body.email,
        name=body.name,
        hashed_password=auth_utils.get_password_hash(body.password),
        auth_provider="email",
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    raw = _set_token(user, "verify", TOKEN_EXPIRY_VERIFY, db)
    send_verification_email(user.email, user.name, raw)

    return {"message": "Account created. Check your email to verify your address."}


# ── email/password login ──────────────────────────────────────────────────────

@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.auth_provider == "google":
        raise HTTPException(
            status_code=400,
            detail="This account uses Google sign-in. Use the 'Continue with Google' button.",
        )
    if not auth_utils.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Check your inbox or request a new verification link.",
        )

    token = auth_utils.create_access_token({"sub": user.email})
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserResponse.model_validate(user),
    )


# ── verify email ──────────────────────────────────────────────────────────────

@router.post("/verify-email", response_model=schemas.TokenResponse)
def verify_email(body: schemas.VerifyEmailRequest, db: Session = Depends(get_db)):
    user = _verify_token(body.token, "verify", db)
    user.is_verified = True
    _clear_token(user, db)
    token = auth_utils.create_access_token({"sub": user.email})
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserResponse.model_validate(user),
    )


# ── resend verification ───────────────────────────────────────────────────────

@router.post("/resend-verification")
def resend_verification(body: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    # Always 200 — don't leak whether email is registered
    if not user or user.auth_provider != "email" or user.is_verified:
        return {"message": "If that address is registered and unverified, a new link has been sent."}
    raw = _set_token(user, "verify", TOKEN_EXPIRY_VERIFY, db)
    send_verification_email(user.email, user.name, raw)
    return {"message": "Verification email resent."}


# ── forgot / reset password ───────────────────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(body: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or user.auth_provider != "email":
        return {"message": "If that address is registered, a reset link has been sent."}
    raw = _set_token(user, "reset", TOKEN_EXPIRY_RESET, db)
    send_password_reset_email(user.email, user.name, raw)
    return {"message": "Password reset email sent."}


@router.post("/reset-password", response_model=schemas.TokenResponse)
def reset_password(body: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user = _verify_token(body.token, "reset", db)
    user.hashed_password = auth_utils.get_password_hash(body.new_password)
    _clear_token(user, db)
    token = auth_utils.create_access_token({"sub": user.email})
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserResponse.model_validate(user),
    )


# ── /me ───────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=schemas.UserResponse)
def me(current_user: models.User = Depends(auth_utils.get_current_user)):
    return current_user


# ── CLI PKCE ──────────────────────────────────────────────────────────────────

class OAuthAuthorizeRequest(BaseModel):
    code_challenge: str
    code_challenge_method: str = "S256"
    client_id: str
    redirect_uri: str


@router.post("/authorize")
def authorize(
    body: OAuthAuthorizeRequest,
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    code = secrets.token_urlsafe(32)
    grant = models.OAuthGrant(
        code=code,
        code_challenge=body.code_challenge,
        code_challenge_method=body.code_challenge_method,
        user_id=current_user.id,
        redirect_uri=body.redirect_uri,
        client_id=body.client_id,
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    db.add(grant)
    db.commit()
    return {"code": code}


@router.post("/token")
def token_exchange(
    grant_type: str = Form(...),
    code: str = Form(...),
    code_verifier: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
    db: Session = Depends(get_db),
):
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="Unsupported grant type")

    grant = db.query(models.OAuthGrant).filter(models.OAuthGrant.code == code).first()
    if not grant:
        raise HTTPException(status_code=400, detail="Invalid authorization code")
    if grant.used:
        raise HTTPException(status_code=400, detail="Authorization code already used")
    if grant.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Authorization code expired")
    if grant.redirect_uri != redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")

    computed = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    if computed != grant.code_challenge:
        raise HTTPException(status_code=400, detail="code_verifier does not match code_challenge")

    grant.used = True
    db.commit()

    user = db.query(models.User).filter(models.User.id == grant.user_id).first()
    access_token = auth_utils.create_access_token({"sub": user.email})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 3600,
        "email": user.email,
        "plan": user.plan,
    }


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.post("/google-callback", response_model=schemas.TokenResponse)
async def google_callback(body: dict, db: Session = Depends(get_db)):
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")
    if not code or not redirect_uri:
        raise HTTPException(status_code=400, detail="code and redirect_uri required")
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange Google code")
        token_data = token_res.json()

        user_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        if user_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch Google user info")
        info = user_res.json()

    google_id = info.get("id")
    email = info.get("email")
    name = info.get("name") or email.split("@")[0]

    user = (
        db.query(models.User).filter(models.User.google_id == google_id).first()
        or db.query(models.User).filter(models.User.email == email).first()
    )

    if user:
        if not user.google_id:
            user.google_id = google_id
            user.auth_provider = "google"
        user.is_verified = True
        db.commit()
    else:
        user = models.User(
            email=email,
            name=name,
            hashed_password="",
            auth_provider="google",
            google_id=google_id,
            is_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = auth_utils.create_access_token({"sub": user.email})
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserResponse.model_validate(user),
    )
