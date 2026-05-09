"""Blog view counter endpoints — public read, public increment."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import BlogView

router = APIRouter()

ADMIN_EMAIL = "bindalshashank.89@gmail.com"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/{slug}/increment", response_model=dict)
def increment_view(slug: str, db: Session = Depends(get_db)):
    """Increment view count for a blog post. Called on page load — no auth required."""
    if len(slug) > 200 or not slug.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid slug")

    record = db.query(BlogView).filter(BlogView.slug == slug).first()
    if record:
        record.view_count += 1
        record.last_viewed_at = datetime.utcnow()
    else:
        record = BlogView(slug=slug, view_count=1, last_viewed_at=datetime.utcnow())
        db.add(record)
    db.commit()
    db.refresh(record)
    return {"slug": record.slug, "views": record.view_count}


@router.get("/{slug}", response_model=dict)
def get_views(slug: str, db: Session = Depends(get_db)):
    """Get view count for a blog post. Public."""
    record = db.query(BlogView).filter(BlogView.slug == slug).first()
    return {"slug": slug, "views": record.view_count if record else 0}


@router.get("/", response_model=list)
def get_all_views(db: Session = Depends(get_db)):
    """Get view counts for all blog posts. Public — used by admin dashboard and blog index."""
    records = db.query(BlogView).order_by(BlogView.view_count.desc()).all()
    return [
        {
            "slug": r.slug,
            "views": r.view_count,
            "last_viewed_at": r.last_viewed_at.isoformat() if r.last_viewed_at else None,
        }
        for r in records
    ]
