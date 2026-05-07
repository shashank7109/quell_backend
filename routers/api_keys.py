import secrets
import hashlib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models
import schemas
import auth as auth_utils
from database import get_db
from schemas import PLANS

router = APIRouter()


def _generate_key() -> tuple[str, str, str]:
    raw = secrets.token_hex(32)
    full_key = f"qk_live_{raw}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    prefix = full_key[:20] + "..."
    return full_key, key_hash, prefix


@router.get("", response_model=list[schemas.APIKeyResponse])
def list_keys(
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.APIKey)
        .filter(models.APIKey.user_id == current_user.id)
        .order_by(models.APIKey.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.APIKeyCreated, status_code=201)
def create_key(
    body: schemas.APIKeyCreate,
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    plan = PLANS[current_user.plan]
    if plan.api_keys != -1:
        count = (
            db.query(models.APIKey)
            .filter(models.APIKey.user_id == current_user.id, models.APIKey.is_active == True)
            .count()
        )
        if count >= plan.api_keys:
            raise HTTPException(
                status_code=403,
                detail=f"Your plan allows {plan.api_keys} API key(s). Upgrade to create more.",
            )

    full_key, key_hash, prefix = _generate_key()
    key = models.APIKey(
        name=body.name,
        key_hash=key_hash,
        key_prefix=prefix,
        user_id=current_user.id,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return schemas.APIKeyCreated(
        id=key.id,
        name=key.name,
        key_prefix=prefix,
        full_key=full_key,
        created_at=key.created_at,
    )


@router.delete("/{key_id}", status_code=204)
def revoke_key(
    key_id: int,
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    key = (
        db.query(models.APIKey)
        .filter(models.APIKey.id == key_id, models.APIKey.user_id == current_user.id)
        .first()
    )
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    key.is_active = False
    db.commit()
