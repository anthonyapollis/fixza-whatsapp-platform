"""End-to-end tests: classifier, matching, and the full WhatsApp conversation."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = ""  # force rule-based classifier in tests

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.classifier import classify
from app.conversation import handle_message, route_message
from app.matching import find_matches, haversine_km
from app.models import Agency, Artisan, Base, Job, Property, Tenant


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    agency = Agency(name="Atlantic Lettings", contact_wa_id="27210000001")
    session.add(agency)
    session.flush()
    prop = Property(agency_id=agency.id, label="Unit 4, 12 Marine Rd",
                    suburb="Sea Point", lat=-33.9203, lng=18.3842)
    session.add(prop)
    session.flush()
    session.add(Tenant(wa_id="27835550001", name="Thandi Mokoena",
                       property_id=prop.id))
    session.add_all([
        Artisan(wa_id="27821", name="Sipho Ndlovu", trade="plumbing",
                suburb="Athlone", lat=-33.9667, lng=18.5167,
                verification_tier="gold", rating=4.8, jobs_completed=42),
        Artisan(wa_id="27822", name="Riaan van Wyk", trade="plumbing",
                suburb="Bellville", lat=-33.9036, lng=18.6293,
                verification_tier="silver", rating=4.5, jobs_completed=18),
        Artisan(wa_id="27823", name="Far Away Plumber", trade="plumbing",
                suburb="Johannesburg", lat=-26.2041, lng=28.0473,
                verification_tier="gold", rating=5.0, jobs_completed=99),
        Artisan(wa_id="27824", name="Fatima Adams", trade="electrical",
                suburb="Woodstock", lat=-33.9271, lng=18.4459,
                verification_tier="gold", rating=4.9, jobs_completed=55),
    ])
    session.commit()
    yield session
    session.close()


# --- classifier ---

def test_classifier_plumbing_urgent():
    r = classify("My geyser burst and the house is flooding, please help ASAP")
    assert r.trade == "plumbing"
    assert r.urgency == "urgent"
    assert r.confidence >= 0.8


def test_classifier_electrical():
    r = classify("The plugs in my kitchen stopped working")
    assert r.trade == "electrical"


def test_classifier_unknown():
    r = classify("I would like to order a pizza")
    assert r.trade is None


# --- matching ---

def test_haversine_known_distance():
    # Cape Town CBD -> Bellville is roughly 20 km
    d = haversine_km(-33.9249, 18.4241, -33.9036, 18.6293)
    assert 18 < d < 22


def test_matching_excludes_out_of_radius_and_ranks(db):
    matches = find_matches(db, "plumbing", -33.9249, 18.4241)
    names = [m.artisan.name for m in matches]
    assert "Far Away Plumber" not in names          # JHB is outside 30 km
    assert names[0] == "Sipho Ndlovu"               # gold + 4.8 + closest wins


# --- conversation flow ---

def _msg(text=None, lat=None, lng=None, wa="27831112222"):
    if lat is not None:
        return {"wa_id": wa, "name": "Test User", "type": "location",
                "lat": lat, "lng": lng}
    return {"wa_id": wa, "name": "Test User", "type": "text", "text": text}


def test_full_booking_flow(db):
    assert "Welcome" in handle_message(db, _msg("hi"))[0]

    reply = handle_message(db, _msg("my geyser is leaking badly"))[0]
    assert "Plumber" in reply and "Where are you" in reply

    reply = handle_message(db, _msg("claremont"))[0]
    assert "Sipho Ndlovu" in reply and "Reply *1*" in reply

    reply = handle_message(db, _msg("1"))[0]
    assert "Booked" in reply and "FZ-" in reply

    job = db.query(Job).one()
    assert job.status == "booked"
    assert job.artisan.name == "Sipho Ndlovu"


def test_location_pin_flow(db):
    handle_message(db, _msg("hi"))
    handle_message(db, _msg("no power in the whole house, urgent!"))
    reply = handle_message(db, _msg(lat=-33.93, lng=18.44))[0]
    assert "Fatima Adams" in reply


def test_unknown_suburb_prompts_again(db):
    handle_message(db, _msg("hi"))
    handle_message(db, _msg("leaking tap"))
    reply = handle_message(db, _msg("polokwane"))[0]
    assert "don't know that area" in reply


def test_cancel_resets(db):
    handle_message(db, _msg("hi"))
    handle_message(db, _msg("leaking tap"))
    reply = handle_message(db, _msg("cancel"))[0]
    assert "cancelled" in reply


def test_status_command(db):
    reply = handle_message(db, _msg("status"))[0]
    assert "no jobs" in reply


# --- agency / tenant flow ---

def test_tenant_flow_skips_location_and_sets_sla(db):
    tenant_wa = "27835550001"
    reply = handle_message(db, _msg("hi", wa=tenant_wa))[0]
    assert "Thandi" in reply and "Marine Rd" in reply and "Atlantic Lettings" in reply

    replies = handle_message(db, _msg("the geyser burst, water everywhere!", wa=tenant_wa))
    joined = "\n".join(replies)
    # No location question — straight to matches from the property's coordinates
    assert "Where are you" not in joined
    assert "Marine Rd" in joined and "Reply *1*" in joined
    assert "4h" in joined  # urgent SLA

    handle_message(db, _msg("1", wa=tenant_wa))
    job = db.query(Job).one()
    assert job.status == "booked"
    assert job.agency_id is not None
    assert job.property_id is not None
    assert job.sla_due_at is not None


def test_regular_customer_still_asked_for_location(db):
    handle_message(db, _msg("hi"))
    reply = handle_message(db, _msg("leaking tap"))[0]
    assert "Where are you" in reply


# --- webhook dispatch (identity-based routing) ---

def test_route_message_sends_artisan_replies_to_artisan_flow(db):
    """Regression test: a live smoke test caught DECLINE from a registered
    artisan's wa_id being swallowed by the customer greeting flow because
    the webhook called handle_message() directly instead of routing by
    identity first. route_message() is the fix — it must never regress."""
    sipho = db.query(Artisan).filter_by(name="Sipho Ndlovu").one()
    job = Job(customer_id=1, artisan_id=sipho.id, description="test",
              trade="plumbing", lat=-33.93, lng=18.43, status="booked")
    db.add(job)
    db.commit()

    reply = route_message(db, _msg("DECLINE", wa=sipho.wa_id))[0]
    assert "welcome" not in reply.lower()   # must NOT hit the customer greeting
    assert "declined" in reply.lower()


def test_route_message_still_greets_regular_customers(db):
    reply = route_message(db, _msg("hi"))[0]
    assert "Welcome" in reply


# --- artisan flow ---

def test_artisan_accept(db):
    from app.artisan_flow import handle_artisan_message
    artisan = db.query(Artisan).filter_by(trade="plumbing").first()

    job = Job(customer_id=1, artisan_id=artisan.id, description="test1",
              trade="plumbing", lat=-33.93, lng=18.43, status="booked")
    db.add(job)
    db.commit()
    reply = handle_artisan_message(db, artisan.wa_id, "ACCEPT")
    assert "accepted" in reply.lower()
    db.commit()
    job = db.get(Job, job.id)
    assert job.status == "accepted"


def test_artisan_decline_auto_reassigns(db):
    """Declining doesn't dead-end the job — the next-best plumber gets it,
    and the decliner's reliability score drops for future matching."""
    from app.artisan_flow import handle_artisan_message
    sipho = db.query(Artisan).filter_by(name="Sipho Ndlovu").one()
    job = Job(customer_id=1, artisan_id=sipho.id, description="test2",
              trade="plumbing", lat=-33.93, lng=18.43, status="booked")
    db.add(job)
    db.commit()

    reply = handle_artisan_message(db, sipho.wa_id, "DECLINE")
    assert "reassigned" in reply.lower()
    db.commit()

    job = db.get(Job, job.id)
    assert job.status == "booked"
    assert job.artisan_id != sipho.id       # handed to the next-best plumber

    sipho = db.get(Artisan, sipho.id)
    assert sipho.declines == 1


def test_artisan_decline_no_alternative_cancels(db):
    """With only one electrician in range, a decline has nowhere to go."""
    from app.artisan_flow import handle_artisan_message
    fatima = db.query(Artisan).filter_by(name="Fatima Adams").one()
    job = Job(customer_id=1, artisan_id=fatima.id, description="test3",
              trade="electrical", lat=-33.93, lng=18.43, status="booked")
    db.add(job)
    db.commit()

    reply = handle_artisan_message(db, fatima.wa_id, "DECLINE")
    assert "no other verified" in reply.lower()
    db.commit()
    job = db.get(Job, job.id)
    assert job.status == "cancelled"


def test_no_show_penalizes_and_reassigns(db):
    """A customer-reported no-show hurts the artisan's reliability score
    more than a decline does — see COMPETITIVE_ANALYSIS.md."""
    sipho = db.query(Artisan).filter_by(name="Sipho Ndlovu").one()
    job = Job(customer_id=1, artisan_id=sipho.id, description="test4",
              trade="plumbing", lat=-33.93, lng=18.43, status="booked")
    db.add(job)
    db.commit()

    reply = handle_message(db, _msg("noshow"))[0]
    assert "no-show" in reply.lower() or "flagged" in reply.lower()

    sipho = db.get(Artisan, sipho.id)
    assert sipho.no_shows == 1


def test_reliability_score_lowers_matching_rank(db):
    """A heavily-declining artisan should rank below an equally-good rival."""
    from app.matching import reliability_score, score_artisan
    sipho = db.query(Artisan).filter_by(name="Sipho Ndlovu").one()
    clean_score = score_artisan(sipho, distance_km=5.0)
    sipho.declines = 5
    penalized_score = score_artisan(sipho, distance_km=5.0)
    assert penalized_score < clean_score
    assert reliability_score(sipho) < 1.0


def test_price_range_shown_in_match_message(db):
    handle_message(db, _msg("hi"))
    handle_message(db, _msg("my geyser is leaking badly"))
    reply = handle_message(db, _msg("claremont"))[0]
    assert "R350" in reply and "R650" in reply


def test_customer_review(db):
    from app.customer_reviews import submit_review
    artisan = db.query(Artisan).first()
    initial_jobs = artisan.jobs_completed
    job = Job(customer_id=1, artisan_id=artisan.id, description="test",
              trade="plumbing", lat=-33.93, lng=18.43, status="completed")
    db.add(job)
    db.flush()
    reply = submit_review(db, job.id, 5, "Excellent work!")
    assert "Thanks" in reply
    artisan = db.get(Artisan, artisan.id)
    assert artisan.rating == 5.0
    assert artisan.jobs_completed == initial_jobs + 1


# --- recurring maintenance scheduling ---

def test_recurring_schedule_creates_job_when_due(db):
    from app.scheduling import create_schedule, run_due_schedules
    prop = db.query(Property).one()
    schedule = create_schedule(db, prop.id, "garden", "Fortnightly garden service", 14)
    db.commit()

    created = run_due_schedules(db)
    db.commit()

    assert len(created) == 1
    job = created[0]
    assert job.trade == "garden"
    assert job.agency_id == prop.agency_id
    assert job.property_id == prop.id
    assert "Scheduled" in job.description

    # next_due_at rolled forward, so a second run finds nothing due yet
    again = run_due_schedules(db)
    assert len(again) == 0
