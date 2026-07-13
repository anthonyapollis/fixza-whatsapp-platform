"""Artisan-side conversation: receive job offer, accept/decline, mark complete & review.

DECLINE auto-reassigns to the next-best-ranked artisan instead of dead-ending
the job — this is the fix for the gap Codex's version left as "an operator can
contact the matched artisans." See COMPETITIVE_ANALYSIS.md: declines/no-shows
also lower the artisan's future rank via matching.reliability_score, which no
major incumbent (Angi/Thumbtack) actually does.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .matching import find_matches
from .models import Artisan, Job, Quote, Review, utcnow


def send_job_offer(db: Session, job: Job) -> str:
    """Craft a WhatsApp job offer message for the assigned artisan."""
    if not job.artisan:
        return ""
    return (
        f"🔧 *New job offer* — FZ-{job.id:05d}\n\n"
        f"*{job.trade.title()}* · {job.suburb}\n"
        f"Urgency: {'🔴 URGENT (4h response)' if job.urgency == 'urgent' else '🟢 Normal (48h response)'}\n\n"
        f"*Job:* {job.description}\n\n"
        f"Reply:\n"
        f"*ACCEPT* to take it\n"
        f"*DECLINE* to pass\n"
        f"*QUOTE 450* (in ZAR) to make an offer"
    )


def handle_artisan_message(db: Session, wa_id: str, text: str) -> str:
    """Process artisan replies: ACCEPT / DECLINE / QUOTE."""
    artisan = db.scalar(select(Artisan).where(Artisan.wa_id == wa_id))
    if not artisan:
        return "You're not registered as an artisan yet. Contact FixZA support."

    lowered = text.lower().strip()

    # Find the most recent booked job assigned to this artisan without an outcome
    pending_job = db.scalar(
        select(Job)
        .where(Job.artisan_id == artisan.id, Job.status == "booked")
        .order_by(Job.id.desc())
    )

    if not pending_job:
        return "No active job offers for you right now."

    if lowered == "accept":
        pending_job.status = "accepted"
        return (
            f"✅ You've accepted FZ-{pending_job.id:05d}. "
            f"Customer will contact you on WhatsApp shortly.\n\n"
            f"Reply *COMPLETE* once the work is finished, "
            f"and the customer can review you."
        )

    if lowered == "decline":
        artisan.declines = (artisan.declines or 0) + 1
        return _reassign_or_cancel(
            db, pending_job, exclude_artisan_id=artisan.id, reason="Declined"
        )

    if lowered.startswith("quote "):
        try:
            amount = float(lowered.split()[1])
            quote = Quote(job_id=pending_job.id, artisan_id=artisan.id, amount_zar=amount)
            db.add(quote)
            return (
                f"💰 Quote of R{amount:.2f} sent for FZ-{pending_job.id:05d}. "
                f"Customer can accept or request a revision."
            )
        except (ValueError, IndexError):
            return "Usage: QUOTE 450 (enter amount in ZAR)"

    if lowered == "complete":
        pending_job.status = "completed"
        return (
            f"✅ Marked FZ-{pending_job.id:05d} complete. "
            f"Customer will review your work and rate you."
        )

    return "Commands: ACCEPT, DECLINE, QUOTE <amount>, COMPLETE"


def _reassign_or_cancel(
    db: Session, job: Job, exclude_artisan_id: int, reason: str = "Declined"
) -> str:
    """Offer the job to the next-best artisan instead of dead-ending it.
    Reliability penalties mean a repeat-decliner naturally sinks in future
    rankings without needing a manual ban.
    """
    candidates = [
        m for m in find_matches(db, job.trade, job.lat, job.lng, limit=5)
        if m.artisan.id != exclude_artisan_id
    ]
    if not candidates:
        job.status = "cancelled"
        return f"{reason} FZ-{job.id:05d}. No other verified artisans are " \
               "available nearby right now — the customer has been notified."

    next_match = candidates[0]
    job.artisan_id = next_match.artisan.id
    job.status = "booked"
    return (
        f"{reason} FZ-{job.id:05d}. Reassigned to {next_match.artisan.name} "
        f"({next_match.distance_km} km away)."
    )


def report_no_show(db: Session, job: Job) -> str:
    """Customer-reported no-show: penalize the artisan and reopen the job."""
    if not job.artisan:
        return "No artisan is assigned to this job."
    job.artisan.no_shows = (job.artisan.no_shows or 0) + 1
    artisan_name = job.artisan.name
    outcome = _reassign_or_cancel(
        db, job, exclude_artisan_id=job.artisan_id, reason="No-show reported"
    )
    return f"Sorry to hear that. We've flagged {artisan_name} for a no-show " \
           f"and lowered their ranking. {outcome}"
