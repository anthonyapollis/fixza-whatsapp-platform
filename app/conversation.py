"""Conversation state machine.

Flow:
  new/greeting -> awaiting_description -> awaiting_location -> awaiting_choice -> booked

Customer messages come in, replies come out as a list of strings (the webhook
layer sends them). All state lives in the sessions table, so restarts are safe.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .artisan_flow import handle_artisan_message, report_no_show
from .classifier import classify
from .matching import PRICE_RANGES, find_matches
from .models import Artisan, ConversationSession, Customer, Job, Tenant
from .models import utcnow

# First-response SLA per urgency (hours) — surfaced on the agency dashboard
SLA_HOURS = {"urgent": 4, "normal": 48}

GREETINGS = {"hi", "hello", "hey", "hallo", "molo", "sawubona", "menu", "start", "help"}
CANCEL_WORDS = {"cancel", "stop", "quit", "0"}

# Fallback geocoding for typed suburb names (Cape Town pilot area).
SUBURB_COORDS: dict[str, tuple[float, float]] = {
    "cape town": (-33.9249, 18.4241),
    "cbd": (-33.9249, 18.4241),
    "sea point": (-33.9203, 18.3842),
    "green point": (-33.9066, 18.4098),
    "woodstock": (-33.9271, 18.4459),
    "observatory": (-33.9376, 18.4713),
    "rondebosch": (-33.9614, 18.4771),
    "claremont": (-33.9836, 18.4655),
    "wynberg": (-34.0057, 18.4599),
    "athlone": (-33.9667, 18.5167),
    "mitchells plain": (-34.0500, 18.6180),
    "khayelitsha": (-34.0403, 18.6778),
    "gugulethu": (-33.9772, 18.5745),
    "bellville": (-33.9036, 18.6293),
    "parow": (-33.9000, 18.6000),
    "durbanville": (-33.8300, 18.6500),
    "milnerton": (-33.8770, 18.4977),
    "table view": (-33.8230, 18.4900),
    "muizenberg": (-34.1081, 18.4699),
    "fish hoek": (-34.1364, 18.4327),
}

WELCOME = (
    "👋 Welcome to *FixZA* — SA's artisans, one WhatsApp away.\n\n"
    "Tell me what you need fixed, e.g.:\n"
    "• _My geyser is leaking_\n"
    "• _No power in my kitchen_\n"
    "• _Need a painter for 2 rooms_\n\n"
    "Reply *cancel* at any time to start over."
)

TRADE_LABELS = {
    "plumbing": "Plumber", "electrical": "Electrician", "carpentry": "Carpenter",
    "painting": "Painter", "appliance_repair": "Appliance technician",
    "building": "Builder", "roofing": "Roofer", "locksmith": "Locksmith",
    "garden": "Garden service", "tiling": "Tiler",
}
TIER_BADGE = {"gold": "🥇 Gold", "silver": "🥈 Silver", "bronze": "🥉 Bronze"}


def _get_or_create_customer(db: Session, wa_id: str, name: str) -> Customer:
    customer = db.scalar(select(Customer).where(Customer.wa_id == wa_id))
    if not customer:
        customer = Customer(wa_id=wa_id, name=name or "")
        db.add(customer)
        db.flush()
    elif name and not customer.name:
        customer.name = name
    return customer


def _get_session(db: Session, wa_id: str) -> ConversationSession:
    session = db.get(ConversationSession, wa_id)
    if not session:
        session = ConversationSession(wa_id=wa_id, state="new")
        db.add(session)
        db.flush()
    return session


def _reset(session: ConversationSession) -> None:
    session.state = "awaiting_description"
    session.pending_job_id = None
    session.offered_artisans = ""


def route_message(db: Session, msg: dict) -> list[str]:
    """Entry point for every inbound WhatsApp message.

    A phone number is either a registered artisan or a customer/tenant —
    never both in this MVP — so identity alone decides which conversation
    engine handles it. This dispatch didn't exist until a live smoke test
    caught an artisan's "DECLINE" being swallowed by the customer greeting
    flow instead of reaching handle_artisan_message.
    """
    wa_id = msg["wa_id"]
    if msg.get("type") == "text":
        artisan = db.scalar(select(Artisan).where(Artisan.wa_id == wa_id))
        if artisan:
            return [handle_artisan_message(db, wa_id, msg.get("text") or "")]
    return handle_message(db, msg)


def handle_message(db: Session, msg: dict) -> list[str]:
    """Process one inbound *customer/tenant* message
    (from whatsapp.extract_messages). Returns reply texts; caller commits.
    """
    wa_id = msg["wa_id"]
    customer = _get_or_create_customer(db, wa_id, msg.get("name", ""))
    session = _get_session(db, wa_id)
    tenant = db.scalar(select(Tenant).where(Tenant.wa_id == wa_id))
    text = (msg.get("text") or "").strip()
    lowered = text.lower()

    # --- global commands ---
    if lowered in CANCEL_WORDS:
        _reset(session)
        return ["No problem, I've cancelled that. " + WELCOME]
    if lowered == "status":
        return [_status_reply(db, customer)]
    if lowered == "noshow":
        return [_handle_no_show(db, customer)]
    if msg.get("type") == "unsupported":
        return ["Sorry, I can only handle text and location messages for now. "
                "Please describe your problem in a message. 🙂"]

    # --- state machine ---
    if session.state in ("new",) or lowered in GREETINGS:
        _reset(session)
        if tenant:
            first_name = (tenant.name or "there").split()[0]
            return [
                f"👋 Hi {first_name}! This is *FixZA* maintenance for "
                f"*{tenant.property.label}, {tenant.property.suburb}* "
                f"(managed by {tenant.property.agency.name}).\n\n"
                "What needs fixing? e.g. _the geyser is leaking_ or "
                "_no power in the kitchen_."
            ]
        return [WELCOME]

    if session.state == "awaiting_description":
        return _handle_description(db, customer, session, text, tenant)

    if session.state == "awaiting_location":
        return _handle_location(db, session, msg, lowered)

    if session.state == "awaiting_choice":
        return _handle_choice(db, session, lowered)

    _reset(session)
    return [WELCOME]


def _handle_description(
    db: Session, customer: Customer, session: ConversationSession,
    text: str, tenant: Tenant | None = None,
) -> list[str]:
    if not text:
        return ["Please describe the problem in a short message, "
                "e.g. _my geyser is leaking_."]
    result = classify(text)
    if not result.trade:
        return ["Hmm, I couldn't work out what kind of artisan you need. 🤔\n"
                "Could you describe it differently? For example:\n"
                "• _burst pipe in the bathroom_\n• _plugs not working_\n"
                "• _need someone to fix my roof_"]
    job = Job(
        customer_id=customer.id,
        description=text,
        trade=result.trade,
        urgency=result.urgency,
        status="draft",
        sla_due_at=utcnow() + timedelta(hours=SLA_HOURS[result.urgency]),
    )
    db.add(job)
    db.flush()
    session.pending_job_id = job.id
    label = TRADE_LABELS[result.trade]
    article = "an" if label[0].lower() in "aeiou" else "a"
    urgent_note = " I can see this is *urgent* — I'll prioritise nearby artisans." \
        if result.urgency == "urgent" else ""

    if tenant:
        # Known tenant: location comes from their property — skip straight to matching
        prop = tenant.property
        job.property_id = prop.id
        job.agency_id = prop.agency_id
        job.lat, job.lng = prop.lat, prop.lng
        job.suburb = prop.suburb
        intro = (f"Got it — you need {article} *{label}* at *{prop.label}*.{urgent_note}\n"
                 f"Logged with {prop.agency.name} "
                 f"(response due within {SLA_HOURS[result.urgency]}h).")
        return [intro] + _present_matches(db, session, job)

    session.state = "awaiting_location"
    return [
        f"Got it — you need {article} *{label}*.{urgent_note}\n\n"
        "📍 Where are you? *Share your location* (attach → location) "
        "or type your suburb, e.g. _Claremont_."
    ]


def _handle_location(
    db: Session, session: ConversationSession, msg: dict, lowered: str
) -> list[str]:
    job = db.get(Job, session.pending_job_id) if session.pending_job_id else None
    if not job:
        _reset(session)
        return ["Something went wrong on my side — let's start again. " + WELCOME]

    if msg.get("type") == "location" and msg.get("lat") is not None:
        job.lat, job.lng = msg["lat"], msg["lng"]
        job.suburb = "shared location"
    elif lowered in SUBURB_COORDS:
        job.lat, job.lng = SUBURB_COORDS[lowered]
        job.suburb = lowered.title()
    else:
        suburbs = ", ".join(sorted(s.title() for s in SUBURB_COORDS)[:8])
        return [f"I don't know that area yet (pilot is Cape Town only). "
                f"Try sharing your pin location, or one of: {suburbs}…"]

    return _present_matches(db, session, job)


def _present_matches(db: Session, session: ConversationSession, job: Job) -> list[str]:
    matches = find_matches(db, job.trade, job.lat, job.lng)
    if not matches:
        job.status = "cancelled"
        _reset(session)
        return [f"😔 Sorry — no verified {TRADE_LABELS[job.trade].lower()}s are "
                "available near you yet. We're growing fast; please try again soon."]

    job.status = "matched"
    session.offered_artisans = ",".join(str(m.artisan.id) for m in matches)
    session.state = "awaiting_choice"

    price_note = ""
    if job.trade in PRICE_RANGES:
        low, high = PRICE_RANGES[job.trade]
        price_note = f" (typical call-out: R{low}–R{high})"

    lines = [f"Here are your top {len(matches)} verified "
             f"{TRADE_LABELS[job.trade].lower()}s near {job.suburb}"
             f"{price_note}:\n"]
    for i, m in enumerate(matches, 1):
        a = m.artisan
        stars = f"{a.rating:.1f}⭐" if a.rating else "New"
        lines.append(
            f"*{i}. {a.name}* — {a.suburb}\n"
            f"   {TIER_BADGE[a.verification_tier]} verified · {stars} · "
            f"{a.jobs_completed} jobs · {m.distance_km} km away"
        )
    lines.append("\nReply *1*, *2* or *3* to book, or *cancel* to start over.")
    return ["\n".join(lines)]


def _handle_choice(db: Session, session: ConversationSession, lowered: str) -> list[str]:
    offered = [int(x) for x in session.offered_artisans.split(",") if x]
    if lowered not in {str(i) for i in range(1, len(offered) + 1)}:
        return [f"Please reply with a number between 1 and {len(offered)}, "
                "or *cancel*."]
    artisan = db.get(Artisan, offered[int(lowered) - 1])
    job = db.get(Job, session.pending_job_id)
    job.artisan_id = artisan.id
    job.status = "booked"
    _reset(session)
    session.state = "awaiting_description"
    agency_note = ""
    if job.agency_id and job.property is not None:
        agency_note = (f"\n{job.property.agency.name} can track this on their "
                       "FixZA dashboard.")
    return [
        f"✅ *Booked!* {artisan.name} ({TIER_BADGE[artisan.verification_tier]} verified) "
        f"has been notified and will contact you on WhatsApp shortly.\n\n"
        f"Job reference: *FZ-{job.id:05d}*{agency_note}\n"
        "Reply *status* to check on it, or describe a new problem anytime."
    ]


def _status_reply(db: Session, customer: Customer) -> str:
    job = db.scalar(
        select(Job).where(Job.customer_id == customer.id).order_by(Job.id.desc())
    )
    if not job:
        return "You have no jobs yet. Describe a problem to get started!"
    artisan = db.get(Artisan, job.artisan_id) if job.artisan_id else None
    who = f" with *{artisan.name}*" if artisan else ""
    return (f"Your latest job *FZ-{job.id:05d}* ({TRADE_LABELS.get(job.trade, job.trade)})"
            f" is *{job.status}*{who}.")


def _handle_no_show(db: Session, customer: Customer) -> str:
    """Customer reports their booked/accepted artisan never arrived.

    See COMPETITIVE_ANALYSIS.md — no incumbent in this category gives the
    algorithm a way to learn from a no-show; this closes that loop and
    auto-reassigns instead of leaving the customer stranded.
    """
    job = db.scalar(
        select(Job)
        .where(Job.customer_id == customer.id, Job.status.in_(("booked", "accepted")))
        .order_by(Job.id.desc())
    )
    if not job:
        return "You don't have an active booked job to report."
    return report_no_show(db, job)
