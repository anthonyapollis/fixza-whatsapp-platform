"""Artisan-side conversation: receive job offer, accept/decline, mark complete & review."""
from sqlalchemy import select
from sqlalchemy.orm import Session

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
        pending_job.status = "cancelled"
        return f"Declined FZ-{pending_job.id:05d}. We'll find another artisan."

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
