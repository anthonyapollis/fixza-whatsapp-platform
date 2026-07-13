# Competitive Analysis — what FixZA borrows and what it deliberately avoids

Home-services marketplaces are a mature category globally. Every major player has
already made — and publicly paid for — the mistakes a new entrant is tempted to
repeat. This document is the reasoning behind FixZA's design choices, not a
generic market overview.

## SweepSouth (South Africa — closest direct comparable)

**What works:** cleaner vetting became the actual product, not a feature —
customers pay a premium specifically for "someone I don't have to worry about."
Recurring weekly/bi-weekly bookings turned one-off transactions into
subscription-like revenue.

**What doesn't:** single-vertical (cleaning only) caps market size; cleaner
churn is high because gig-economy pay is thin and unpredictable; the platform
carries all the trust risk while cleaners carry all the income risk.

**Applied to FixZA:**
- Verification tiers (🥉🥈🥇) already mirror SweepSouth's core insight — keep it.
- Multi-trade from day one (10 trades vs. one) avoids the ceiling SweepSouth hit.
- New in this update: **recurring maintenance schedules** for agency
  properties (§3 below) — the subscription-revenue lesson, applied to B2B
  instead of consumer, which is a better fit for SA property management.

## Thumbtack / Angi (HomeAdvisor) — the pay-per-lead cautionary tale

**What works:** wide category coverage, professionals pay based on intent to
convert, not a flat listing fee.

**What doesn't — this is the single most-repeated complaint about this
category:** the *same lead* is sold to 3–5 competing pros simultaneously.
Customers get spammed with calls from strangers; pros pay for leads that were
never real intent, or that a competitor closed first. Review-manipulation
accusations (paid placement affecting "recommended" rankings) followed Angi
for years.

**Applied to FixZA:**
- FixZA never resells a job. The customer sees exactly 3 ranked options and
  *chooses one* — the other two are never contacted. This was already the
  design; it's worth stating explicitly as a deliberate anti-pattern avoidance.
- Ranking must never be for sale. There's no "paid placement" concept in
  `matching.py` and there must never be one — it's the trust foundation.

## TaskRabbit / Airtasker — the race-to-the-bottom bidding problem

**What works:** flexible task types beyond fixed trades, tasker profiles with
granular reviews.

**What doesn't:** open bidding pushes taskers to underprice, which correlates
with rushed or lower-quality work; customers have no price anchor and
frequently feel a "final" price crept up after booking.

**Applied to FixZA (new in this update):**
- **Upfront estimated price ranges per trade**, shown at match time — the
  customer sees "R350–R650 call-out" before choosing an artisan, not after.
  No bidding war, no surprise. See `PRICE_RANGES` in `matching.py`.

## Urban Company (India) — the best-run version of this business model

**What works:** standardized, non-negotiable pricing; provider training
academies; in-app everything (booking, tracking, payment); insurance bundled
into every job. This is the platform to study for "how do you make this feel
premium, not gig-economy."

**What doesn't:** provider protests over algorithm-driven pay cuts and rising
commission (25–30%) show what happens when the matching algorithm optimizes
purely for platform margin instead of being legible to the people it ranks.

**Applied to FixZA:**
- The matching formula (`matching.py`) is a simple, documented weighted sum —
  not a black box. An artisan should be able to understand *why* they didn't
  get offered a job (distance, rating, tier, reliability) and improve it.
- No commission-squeeze mechanic exists in this codebase, and the
  verification-cost-recovery model (spread over first jobs, not charged
  upfront) was chosen specifically to keep the artisan's downside low —
  see the earlier ChatGPT research this project started from.

## The real incumbent: WhatsApp groups and word of mouth

This is what FixZA actually competes with in SA today, not the international
apps above. Its strength is zero friction and a trusted personal
recommendation. Its weaknesses are exactly what FixZA is built to fix: no
verification, no accountability if the job goes badly, no history, and
whoever replies fastest in the group chat gets the work regardless of whether
they're actually available or good.

**Applied to FixZA:** everything in this codebase — verification tiers, SLA
tracking, review-gated ratings, a documented matching algorithm — is the
structured version of "ask the group chat," kept in the one interface (WhatsApp)
people already trust for this.

---

## Concrete changes made in this update

1. **Artisan reliability scoring** (`app/matching.py`, `app/artisan_flow.py`) —
   declines and no-shows now measurably lower an artisan's rank, so the
   algorithm self-corrects instead of repeatedly offering jobs to unreliable
   artisans. Directly targets the Angi/Thumbtack "no accountability for
   pros" gap.
2. **Upfront price transparency** (`app/matching.py`) — estimated ZAR ranges
   per trade shown before booking. Directly targets the TaskRabbit/Airtasker
   bidding-war and price-surprise complaints.
3. **Recurring maintenance scheduling for agencies** (`app/models.py`,
   `app/scheduling.py`) — property agencies can set up recurring inspection/
   garden/pool-service jobs instead of only reactive breakdowns. Directly
   targets the SweepSouth lesson that one-off transactional revenue caps
   growth, applied to the B2B pivot instead of consumer subscriptions.
