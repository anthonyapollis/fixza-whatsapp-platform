"""SQLAlchemy 2.0 models — mirrors db/schema.sql (Postgres/Supabase)."""
from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Integer, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    wa_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # WhatsApp number
    name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    jobs: Mapped[list["Job"]] = relationship(back_populates="customer")


class Artisan(Base):
    __tablename__ = "artisans"

    id: Mapped[int] = mapped_column(primary_key=True)
    wa_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    trade: Mapped[str] = mapped_column(String(40), index=True)   # plumbing, electrical, ...
    suburb: Mapped[str] = mapped_column(String(80), default="")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    # bronze / silver / gold — tiered verification model
    verification_tier: Mapped[str] = mapped_column(String(10), default="bronze")
    rating: Mapped[float] = mapped_column(Float, default=0.0)       # 0..5
    jobs_completed: Mapped[int] = mapped_column(Integer, default=0)
    # Reliability tracking: declines and no-shows pull rank down over time.
    # See COMPETITIVE_ANALYSIS.md — this is what Angi/Thumbtack never built,
    # and it's why "top match" on those platforms doesn't mean "will show up."
    declines: Mapped[int] = mapped_column(Integer, default=0)
    no_shows: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Agency(Base):
    """Rental agency / body corporate — the B2B customer paying per door."""
    __tablename__ = "agencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    contact_wa_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"), index=True)
    label: Mapped[str] = mapped_column(String(160))   # "Unit 4, 12 Marine Rd"
    suburb: Mapped[str] = mapped_column(String(80), default="")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)

    agency: Mapped["Agency"] = relationship()


class Tenant(Base):
    """Known tenant — recognised by WhatsApp number, tied to a property."""
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    wa_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"))

    property: Mapped["Property"] = relationship()


class RecurringSchedule(Base):
    """Recurring maintenance for an agency property (garden, pool, inspection).

    Applies the SweepSouth lesson (recurring bookings beat one-off jobs for
    revenue predictability) to the B2B side instead of consumer subscriptions
    — see COMPETITIVE_ANALYSIS.md.
    """
    __tablename__ = "recurring_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    trade: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    frequency_days: Mapped[int] = mapped_column(Integer)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    property: Mapped["Property"] = relationship()


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    artisan_id: Mapped[int | None] = mapped_column(ForeignKey("artisans.id"), nullable=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), nullable=True)
    agency_id: Mapped[int | None] = mapped_column(ForeignKey("agencies.id"), index=True, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    trade: Mapped[str] = mapped_column(String(40), index=True)
    urgency: Mapped[str] = mapped_column(String(10), default="normal")  # normal | urgent
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    suburb: Mapped[str] = mapped_column(String(80), default="")
    # draft -> matched -> booked -> completed | cancelled
    status: Mapped[str] = mapped_column(String(15), default="draft", index=True)
    # SLA: when a first artisan response is due (urgent 4h, normal 48h)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="jobs")
    artisan: Mapped["Artisan"] = relationship()
    property: Mapped["Property"] = relationship()


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    artisan_id: Mapped[int] = mapped_column(ForeignKey("artisans.id"))
    amount_zar: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|accepted|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    artisan_id: Mapped[int] = mapped_column(ForeignKey("artisans.id"), index=True)
    stars: Mapped[int] = mapped_column(Integer)  # 1..5
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationSession(Base):
    """Per-customer conversation state so the bot survives restarts."""
    __tablename__ = "sessions"

    wa_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(30), default="new")
    pending_job_id: Mapped[int | None] = mapped_column(nullable=True)
    # Comma-separated artisan ids offered as options 1..3
    offered_artisans: Mapped[str] = mapped_column(String(60), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MessageLog(Base):
    """Audit log of every inbound/outbound message (POPIA: minimal PII, purge policy)."""
    __tablename__ = "message_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    wa_id: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(3))  # in | out
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
