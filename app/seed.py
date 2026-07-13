"""Seed the database with pilot Cape Town artisans + a demo rental agency.

Usage:  python -m app.seed
"""
from .db import SessionLocal, init_db
from .models import Agency, Artisan, Property, Tenant
from .scheduling import create_schedule

ARTISANS = [
    # name, wa_id, trade, suburb, lat, lng, tier, rating, jobs
    ("Sipho Ndlovu", "27820000001", "plumbing", "Athlone", -33.9667, 18.5167, "gold", 4.8, 42),
    ("Riaan van Wyk", "27820000002", "plumbing", "Bellville", -33.9036, 18.6293, "silver", 4.5, 18),
    ("Thabo Mokoena", "27820000003", "plumbing", "Khayelitsha", -34.0403, 18.6778, "bronze", 4.2, 6),
    ("Fatima Adams", "27820000004", "electrical", "Woodstock", -33.9271, 18.4459, "gold", 4.9, 55),
    ("Johan Botha", "27820000005", "electrical", "Parow", -33.9000, 18.6000, "silver", 4.3, 21),
    ("Luyanda Mbeki", "27820000006", "electrical", "Gugulethu", -33.9772, 18.5745, "bronze", 4.0, 4),
    ("Pieter Smit", "27820000007", "carpentry", "Observatory", -33.9376, 18.4713, "silver", 4.6, 15),
    ("Nomsa Dlamini", "27820000008", "painting", "Claremont", -33.9836, 18.4655, "gold", 4.7, 33),
    ("Ahmed Khan", "27820000009", "appliance_repair", "Rondebosch", -33.9614, 18.4771, "silver", 4.4, 12),
    ("David Jacobs", "27820000010", "roofing", "Mitchells Plain", -34.0500, 18.6180, "bronze", 3.9, 8),
    ("Grant Petersen", "27820000011", "locksmith", "Sea Point", -33.9203, 18.3842, "silver", 4.5, 27),
    ("Zanele Khumalo", "27820000012", "tiling", "Wynberg", -34.0057, 18.4599, "gold", 4.8, 39),
    ("Marius Coetzee", "27820000013", "building", "Durbanville", -33.8300, 18.6500, "silver", 4.1, 11),
    ("Sam Naidoo", "27820000014", "garden", "Milnerton", -33.8770, 18.4977, "bronze", 4.3, 9),
    ("Lindiwe Sithole", "27820000015", "plumbing", "Sea Point", -33.9203, 18.3842, "silver", 4.6, 24),
]


def run() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.query(Artisan).count():
            print("Artisans already seeded — skipping.")
            return
        for name, wa, trade, suburb, lat, lng, tier, rating, jobs in ARTISANS:
            db.add(Artisan(
                name=name, wa_id=wa, trade=trade, suburb=suburb, lat=lat, lng=lng,
                verification_tier=tier, rating=rating, jobs_completed=jobs,
            ))

        # Demo B2B customer: rental agency with 3 managed properties + tenants
        agency = Agency(name="Atlantic Lettings", contact_wa_id="27210000001")
        db.add(agency)
        db.flush()
        props = [
            Property(agency_id=agency.id, label="Unit 4, 12 Marine Rd",
                     suburb="Sea Point", lat=-33.9203, lng=18.3842),
            Property(agency_id=agency.id, label="7 Protea Ave",
                     suburb="Claremont", lat=-33.9836, lng=18.4655),
            Property(agency_id=agency.id, label="Loft 2, Old Biscuit Mill",
                     suburb="Woodstock", lat=-33.9271, lng=18.4459),
        ]
        db.add_all(props)
        db.flush()
        db.add_all([
            Tenant(wa_id="27835550001", name="Thandi Mokoena", property_id=props[0].id),
            Tenant(wa_id="27835550002", name="James Carter", property_id=props[1].id),
            Tenant(wa_id="27835550003", name="Aisha Patel", property_id=props[2].id),
        ])
        db.flush()

        # Demo recurring maintenance — the SweepSouth-style predictable revenue play
        create_schedule(db, props[2].id, "garden", "Fortnightly garden service", 14)

        db.commit()
        print(f"Seeded {len(ARTISANS)} artisans, 1 agency, "
              f"{len(props)} properties, 3 tenants, 1 recurring schedule.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
