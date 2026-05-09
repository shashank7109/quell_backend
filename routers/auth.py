from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import base64, hashlib, secrets
import httpx
import models
import schemas
import auth as auth_utils
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from database import get_db
from pydantic import BaseModel


class OAuthAuthorizeRequest(BaseModel):
    code_challenge: str
    code_challenge_method: str = "S256"
    client_id: str
    redirect_uri: str

router = APIRouter()


@router.post("/register", response_model=schemas.TokenResponse)
def register(body: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = models.User(
        email=body.email,
        name=body.name,
        hashed_password=auth_utils.get_password_hash(body.password),
        auth_provider="email",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = auth_utils.create_access_token({"sub": user.email})
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserResponse.model_validate(user),
    )


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.auth_provider == "google":
        raise HTTPException(status_code=400, detail="This account uses Google sign-in")
    if not auth_utils.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = auth_utils.create_access_token({"sub": user.email})
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserResponse.model_validate(user),
    )


@router.get("/me", response_model=schemas.UserResponse)
def me(current_user: models.User = Depends(auth_utils.get_current_user)):
    return current_user


@router.post("/authorize")
def authorize(
    body: OAuthAuthorizeRequest,
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    """Create a short-lived PKCE authorization code for the CLI."""
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
    """Exchange a PKCE authorization code for an access token."""
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

    # PKCE S256 verification
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


@router.post("/google-callback", response_model=schemas.TokenResponse)
async def google_callback(body: dict, db: Session = Depends(get_db)):
    """Exchange a Google OAuth code for a Quell JWT."""
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")
    if not code or not redirect_uri:
        raise HTTPException(status_code=400, detail="code and redirect_uri required")
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    async with httpx.AsyncClient() as client:
        # Exchange code for tokens
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

        # Fetch user info
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

    # Find existing user by google_id or email
    user = (
        db.query(models.User).filter(models.User.google_id == google_id).first()
        or db.query(models.User).filter(models.User.email == email).first()
    )

    if user:
        # Link google_id if signed up with email first
        if not user.google_id:
            user.google_id = google_id
            user.auth_provider = "google"
            db.commit()
    else:
        user = models.User(
            email=email,
            name=name,
            hashed_password="",
            auth_provider="google",
            google_id=google_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = auth_utils.create_access_token({"sub": user.email})
    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserResponse.model_validate(user),
    )
