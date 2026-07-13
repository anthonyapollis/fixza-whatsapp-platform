"""Customer reviews artisan after job completion."""
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .models import Artisan, Job, Review


def submit_review(db: Session, job_id: int, stars: int, comment: str = "") -> str:
    """Customer rates a completed job."""
    if not 1 <= stars <= 5:
        return "Rating must be 1–5 stars."
    job = db.get(Job, job_id)
    if not job or job.status != "completed":
        return f"Job FZ-{job_id:05d} not found or not yet complete."
    if not job.artisan:
        return "No artisan assigned."

    # Check for duplicate review
    existing = db.scalar(select(Review).where(Review.job_id == job_id))
    if existing:
        return f"You've already reviewed this job."

    review = Review(job_id=job_id, artisan_id=job.artisan_id, stars=stars, comment=comment)
    db.add(review)

    # Recalculate artisan rating
    artisan = job.artisan
    avg = db.scalar(
        select(func.avg(Review.stars)).where(Review.artisan_id == artisan.id)
    )
    artisan.rating = float(avg) if avg else 0.0
    artisan.jobs_completed = (artisan.jobs_completed or 0) + 1

    db.commit()
    badge = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}[stars]
    return (
        f"✅ Thanks for the {badge}! Your rating helps other customers find great artisans.\n"
        f"{artisan.name}'s new rating: {artisan.rating:.1f}⭐ "
        f"({artisan.jobs_completed} jobs)"
    )
