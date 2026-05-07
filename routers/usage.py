from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from collections import defaultdict
import models
import schemas
import auth as auth_utils
from database import get_db

router = APIRouter()


@router.get("/summary", response_model=schemas.UsageSummary)
def usage_summary(
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    this_month = (
        db.query(models.UsageRecord)
        .filter(
            models.UsageRecord.user_id == current_user.id,
            models.UsageRecord.timestamp >= month_start,
        )
        .count()
    )
    total = (
        db.query(models.UsageRecord)
        .filter(models.UsageRecord.user_id == current_user.id)
        .count()
    )

    # Daily breakdown for the last 14 days
    cutoff = now - timedelta(days=14)
    records = (
        db.query(models.UsageRecord)
        .filter(
            models.UsageRecord.user_id == current_user.id,
            models.UsageRecord.timestamp >= cutoff,
        )
        .all()
    )
    daily: dict[str, int] = defaultdict(int)
    for r in records:
        daily[r.timestamp.strftime("%Y-%m-%d")] += 1

    daily_list = [
        {"date": (now - timedelta(days=i)).strftime("%Y-%m-%d"), "count": 0}
        for i in range(13, -1, -1)
    ]
    for entry in daily_list:
        entry["count"] = daily.get(entry["date"], 0)

    from schemas import PLANS
    plan = PLANS[current_user.plan]
    return schemas.UsageSummary(
        this_month=this_month,
        monthly_limit=plan.fixes_per_month,
        total_all_time=total,
        daily=daily_list,
    )


@router.get("/history", response_model=list[schemas.UsageRecord])
def usage_history(
    page: int = 1,
    limit: int = 20,
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.UsageRecord)
        .filter(models.UsageRecord.user_id == current_user.id)
        .order_by(models.UsageRecord.timestamp.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    results = []
    for r in records:
        prefix = None
        if r.api_key_id:
            key = db.query(models.APIKey).filter(models.APIKey.id == r.api_key_id).first()
            if key:
                prefix = key.key_prefix
        results.append(
            schemas.UsageRecord(
                id=r.id,
                action=r.action,
                mutant_id=r.mutant_id,
                api_key_prefix=prefix,
                timestamp=r.timestamp,
            )
        )
    return results
