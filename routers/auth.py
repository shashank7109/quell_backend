from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import httpx
import models
import schemas
import auth as auth_utils
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from database import get_db

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
