import razorpay
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models
import schemas
import auth as auth_utils
from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
from database import get_db
from schemas import PLANS

router = APIRouter()

# Razorpay amounts in paise (INR × 100)
PLAN_PRICES_PAISE: dict[str, int] = {
    "pro": 159900,   # ₹1,599 / month
    "team": 659900,  # ₹6,599 / month
}


def _razorpay_client() -> razorpay.Client:
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=500, detail="Razorpay not configured")
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


@router.get("/plan")
def get_plan(current_user: models.User = Depends(auth_utils.get_current_user)):
    plan = PLANS[current_user.plan]
    return {"current_plan": current_user.plan, "details": plan.model_dump()}


@router.get("/plans")
def list_plans():
    return {k: v.model_dump() for k, v in PLANS.items()}


@router.post("/create-order")
def create_order(
    body: dict,
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    plan = body.get("plan")
    if plan not in PLAN_PRICES_PAISE:
        raise HTTPException(status_code=400, detail="Invalid plan for payment")

    client = _razorpay_client()
    order = client.order.create({
        "amount": PLAN_PRICES_PAISE[plan],
        "currency": "INR",
        "receipt": f"quell_plan_{plan}_user_{current_user.id}",
        "notes": {"plan": plan, "user_id": str(current_user.id)},
    })
    return {
        "order_id": order["id"],
        "amount": PLAN_PRICES_PAISE[plan],
        "currency": "INR",
        "key_id": RAZORPAY_KEY_ID,
    }


@router.post("/verify-payment")
def verify_payment(
    body: dict,
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    plan = body.get("plan")
    if plan not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    client = _razorpay_client()
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": body["razorpay_order_id"],
            "razorpay_payment_id": body["razorpay_payment_id"],
            "razorpay_signature": body["razorpay_signature"],
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    current_user.plan = plan
    db.commit()

    # Refresh user cache key in localStorage is updated by frontend
    return {"message": f"Upgraded to {plan}", "plan": plan}


@router.post("/upgrade")
def upgrade_plan(
    body: dict,
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    """Direct upgrade (no payment) — used for downgrades or dev/test."""
    new_plan = body.get("plan")
    if new_plan not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")
    if new_plan == current_user.plan:
        raise HTTPException(status_code=400, detail="Already on this plan")
    current_user.plan = new_plan
    db.commit()
    return {"message": f"Plan changed to {new_plan}", "plan": new_plan}
