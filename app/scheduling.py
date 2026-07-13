"""Recurring maintenance scheduling for agency properties.

Turns FixZA from a purely reactive marketplace ("something broke, help") into
one with predictable recurring revenue for agencies (garden service every
14 days, pool every 7, fire-safety inspection every 90) — the SweepSouth
lesson applied to B2B. See COMPETITIVE_ANALYSIS.md.

Render's free tier has no background worker, so `run_due_schedules` is exposed
as an endpoint (`POST /admin/run-schedules`) meant to be hit by an external
cron (e.g. cron-job.org, GitHub Actions schedule) once a day. This is a
deliberate, documented tradeoff, not an oversight — see DEPLOY.md.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Customer, Job, RecurringSchedule, utcnow


def create_schedule(
    db: Session, property_id: int, trade: str, description: str, frequency_days: int
) -> RecurringSchedule:
    schedule = RecurringSchedule(
        property_id=property_id,
        trade=trade,
        description=description,
        frequency_days=frequency_days,
        next_due_at=utcnow(),
    )
    db.add(schedule)
    db.flush()
    return schedule


def run_due_schedules(db: Session) -> list[Job]:
    """Create a Job for every schedule that's due, then roll next_due_at forward.

    Returns the list of newly created jobs (unmatched — the agency dashboard
    or a follow-up matching pass assigns an artisan, same as any other job).
    """
    due = db.scalars(
        select(RecurringSchedule).where(
            RecurringSchedule.active == 1, RecurringSchedule.next_due_at <= utcnow()
        )
    ).all()

    created: list[Job] = []
    for schedule in due:
        prop = schedule.property
        # Recurring jobs are logged against the agency's own contact number so
        # they show up on the dashboard even when no tenant is WhatsApp-active.
        agency_wa_id = prop.agency.contact_wa_id or f"agency-{prop.agency_id}"
        customer = db.scalar(select(Customer).where(Customer.wa_id == agency_wa_id))
        if not customer:
            customer = Customer(wa_id=agency_wa_id, name=prop.agency.name)
            db.add(customer)
            db.flush()

        job = Job(
            customer_id=customer.id,
            property_id=prop.id,
            agency_id=prop.agency_id,
            description=f"[Scheduled] {schedule.description}",
            trade=schedule.trade,
            urgency="normal",
            lat=prop.lat,
            lng=prop.lng,
            suburb=prop.suburb,
            status="draft",
        )
        db.add(job)
        created.append(job)
        schedule.next_due_at = utcnow() + timedelta(days=schedule.frequency_days)

    return created
