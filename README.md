# FixZA — SA's artisans. One WhatsApp away. 🇿🇦

A WhatsApp-first marketplace that connects South African customers with **verified
artisans** (plumbers, electricians, painters, and more). No app to download — the
entire customer experience runs inside WhatsApp.

Built with **Python + FastAPI**, the **WhatsApp Business Platform (Cloud API)**,
**PostgreSQL (Supabase)**, and optional **Claude AI** job classification.

```
Customer ──▶ WhatsApp ──▶ Meta Cloud API ──▶ FastAPI (Render)
                                                │
                              ┌─────────────────┼──────────────────┐
                              ▼                 ▼                  ▼
                       AI classifier     Matching engine    Supabase PostgreSQL
                     (rules + Claude)  (distance · rating   customers · artisans
                                        · tier · history)   jobs · quotes · reviews
                                                │
                                                ▼
                                     /stats  ──▶  Power BI dashboard
```

## Features

- **Conversation state machine** — greeting → describe problem → share location →
  pick from top 3 matches → booked. State is DB-backed, so restarts are safe.
- **Hybrid AI job classification** — instant keyword rules (10 trades, urgency
  detection); low-confidence messages escalate to Claude if `ANTHROPIC_API_KEY` is set.
- **Matching engine** — haversine distance (30 km radius) + rating + verification
  tier (🥉🥈🥇) + jobs completed, weighted into a single score.
- **Webhook security** — verifies Meta's `X-Hub-Signature-256` HMAC on every POST.
- **Dry-run mode** — no WhatsApp token? Outbound messages print to the console, so
  the full flow is testable locally with zero Meta setup.
- **Landing page** — themed marketing site served at `/` (Mzansi / Safari Dusk /
  Global themes with a live theme switcher).
- **Property-agency layer (B2B)** — agencies, properties, and tenants. Known
  tenants are recognised by WhatsApp number, skip the location step (the
  property's coordinates are used), and every job is logged against the agency
  with a first-response SLA (urgent 4h / normal 48h). Agency dashboard at
  `/agency/{id}` (HTML) and `/agency/{id}/jobs` (JSON), with SLA-overdue flags.
- **Ops endpoint** — `/stats` returns JSON for Power BI's web connector.
- **POPIA-aware** — message log retention policy included in the schema.

## Quick start (local, no accounts needed)

```powershell
cd fixza-whatsapp-platform
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.seed                     # seed 15 Cape Town pilot artisans
uvicorn app.main:app --reload
```

- Landing page: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Run tests: `pytest`

Simulate a WhatsApp message locally (dry-run mode prints the bot's replies):

```powershell
curl -X POST http://127.0.0.1:8000/webhook -H "Content-Type: application/json" -d '{\"entry\":[{\"changes\":[{\"value\":{\"contacts\":[{\"wa_id\":\"27831234567\",\"profile\":{\"name\":\"Thandi\"}}],\"messages\":[{\"from\":\"27831234567\",\"type\":\"text\",\"text\":{\"body\":\"hi\"}}]}}]}]}'
```

## Going live — registration checklist

| Step | Where | What you get |
|------|-------|--------------|
| 1 | [GitHub](https://github.com) | Repo to deploy from |
| 2 | [Meta for Developers](https://developers.facebook.com) → Create App → *Business* type → add **WhatsApp** product | App ID, App Secret, temp access token, test phone number |
| 3 | [Meta Business Suite](https://business.facebook.com) | WhatsApp Business Account (WABA), permanent phone number, message templates |
| 4 | [Supabase](https://supabase.com) → New project → SQL Editor → run `db/schema.sql` | PostgreSQL + connection string |
| 5 | [Render](https://render.com) → New Web Service → connect repo (`render.yaml` is auto-detected) | Public HTTPS URL for the webhook |

Then in the Meta dashboard → WhatsApp → Configuration:

1. **Callback URL**: `https://<your-app>.onrender.com/webhook`
2. **Verify token**: same value as `WHATSAPP_VERIFY_TOKEN` in your env
3. Subscribe to the **messages** webhook field.

Set the env vars on Render (see `.env.example`), redeploy, and message your
WhatsApp test number: **"My geyser is leaking"**.

Local webhook testing without deploying: `ngrok http 8000` and use the ngrok
URL as the callback.

## Project layout

```
app/
  main.py          FastAPI app: webhook, landing page, /stats
  conversation.py  State machine (greeting → description → location → choice → booked)
  classifier.py    Keyword + optional Claude job classification
  matching.py      Haversine + weighted artisan scoring
  whatsapp.py      Cloud API client, signature verification, payload parsing
  models.py        SQLAlchemy models
  db.py            Engine/session (SQLite locally, Supabase in prod)
  seed.py          15 pilot artisans (Cape Town)
  static/index.html  Themed landing page
db/schema.sql      Canonical Postgres schema for Supabase
tests/test_flow.py End-to-end tests (classifier, matching, full booking flow)
render.yaml        One-click Render deployment
```

## Roadmap

- Artisan-side WhatsApp flow (accept/decline jobs, send quotes)
- Payments (Payfast/Ozow escrow) + verification-cost recovery from first jobs
- Review collection after job completion
- Interactive WhatsApp list messages instead of "reply 1/2/3"
- Power BI operational dashboard on `/stats`
- Expansion beyond the Cape Town pilot

## Legal / IP notes

- Brand: register **FixZA** as a trade mark via [CIPC](https://www.cipc.co.za)
  (Nice classes for tech platform + repair services) before heavy marketing spend.
- All background checks require candidate consent and POPIA-compliant handling.
- Keep the matching weights and anti-bypass logic as trade secrets.
