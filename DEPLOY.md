# Deployment Checklist — FixZA to production

## Pre-flight (Before you start)

- [ ] Choose a business name and check domain availability (e.g., fixza.co.za)
- [ ] Register trade mark via [CIPC](https://www.cipc.co.za) (Nice classes for tech platform + repair services)
- [ ] Verify your WhatsApp Business Account can use the Cloud API (Meta approval can take 24–48h)

## Step 1: Meta Developer Setup (2–5 min)

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Create a **Business** type app
3. Add the **WhatsApp** product
4. Navigate to **WhatsApp > Getting started**
   - You'll see a temporary **test phone number** (use this to verify locally with ngrok first)
   - Note your **App ID** and **App Secret**
5. Click **Create a Business Account**
6. In **Meta Business Suite**, create your WhatsApp Business Account (WABA) and claim a real phone number
   - This will replace the test number

## Step 2: Database (Supabase) — 2 min

1. Go to [supabase.com](https://supabase.com) → **New project**
2. Name it `fixza-prod`, choose region closest to Cape Town (or EU)
3. Wait for database creation (~1 min)
4. Go to **Project Settings** > **Database** > copy the **Connection string**
   - Format: `postgresql+psycopg2://postgres:<password>@db.<ref>.supabase.co:5432/postgres`
5. Go to **SQL Editor**, paste the contents of `db/schema.sql`, run it
6. (Optional) seed your artisans via the Supabase dashboard

## Step 3: Render Deployment — 5 min

1. Go to [render.com](https://render.com) → Sign up / Log in
2. **Connect your GitHub repository** (click "New+" → Web Service → GitHub)
   - Select the `fixza-whatsapp-platform` repo
   - Root directory: `.` (current)
   - Build command: (Render auto-detects `render.yaml`)
3. Environment variables (these map to your `.env`):
   - `WHATSAPP_TOKEN` — from Meta Developer dashboard (get a system-user access token or production token)
   - `WHATSAPP_PHONE_NUMBER_ID` — from Meta WABA settings
   - `WHATSAPP_VERIFY_TOKEN` — choose a strong random string (keep it secret)
   - `META_APP_SECRET` — from Meta Developer app settings
   - `DATABASE_URL` — paste your Supabase connection string from Step 2
   - `ANTHROPIC_API_KEY` — (optional) if using Claude for job classification
4. Click **Deploy**
5. Render will show a live URL like `https://fixza-api-abc123.onrender.com`

## Step 4: Meta Webhook Configuration — 2 min

1. In [Meta for Developers](https://developers.facebook.com), go to your WhatsApp app
2. Navigate to **WhatsApp > Configuration**
3. **Webhook URL**: paste your Render URL + `/webhook`
   - Example: `https://fixza-api-abc123.onrender.com/webhook`
4. **Verify token**: use the same value you set in Render's `WHATSAPP_VERIFY_TOKEN`
5. Click **Verify and save**
   - Meta will POST a challenge to your webhook endpoint; if it responds correctly, you're verified
6. Subscribe to **messages** webhook field

## Step 5: Agency Onboarding (in your app code)

You now need a way to register agencies (rental managers), properties, and tenants. For MVP:

**Via Supabase dashboard directly:**
1. Go to Supabase → **Table Editor**
2. Insert an agency: `name="Your Agency"`, `contact_wa_id="27..." `
3. Insert properties with `agency_id`, `label`, `lat`/`lng`
4. Insert tenants with their WhatsApp numbers and `property_id`

**Better: add a simple admin endpoint** (future sprint):
```
POST /admin/agency
POST /admin/property
POST /admin/tenant
```

For now, seed a demo agency to show the flow.

## Step 6: Test the live flow

1. Send a WhatsApp message to your WABA number from a real phone (not the test number)
2. It should hit your `/webhook` endpoint on Render
3. The conversation should play out: greeting → describe problem → location (if not a known tenant) → artisan match → book

## Monitoring & Maintenance

- **Render dashboard**: watch CPU, memory, build logs
- **Supabase dashboard**: monitor database rows, query stats
- **Message log**: in Supabase, `message_log` table grows daily; implement retention (`delete from message_log where created_at < now() - interval '90 days'`) via Supabase cron or a scheduled Render worker
- **Artisan onboarding**: build a simple form or WhatsApp flow to register new artisans and verify them

## Cost estimate (2026)

| Component | Free tier | Paid tier (100 artisans, 500 jobs/month) |
|-----------|-----------|----------------------------------------|
| Meta (WhatsApp API) | test only | ~R1000–5000/month (volume-based) |
| Supabase | 500MB DB | ~R500–2000/month (storage + egress) |
| Render | 750 free hours | ~R2000–4000/month (for 2 dynos) |
| Anthropic (Claude) | per-request | ~R500/month (if classification on) |
| **Total** | ~$0 | ~R4000–11000/month (R$1–2 per job) |

## Known limitations (MVP)

- No payment processing yet (Payfast / Ozow for escrow)
- No verification cost recovery logic yet
- No artisan availability hours / scheduling
- No multi-language support (English + Zulu / Xhosa for SA expansion)
- Dashboard is HTML only (no auth layer — add OAuth before production)

## Post-launch roadmap

1. **Artisan mobile app** (Flutter) — faster than WhatsApp for complex workflows
2. **Payment integration** — Payfast or Ozow escrow; calculate and deduct verification costs
3. **SMS fallback** — some artisans may prefer SMS (Twilio integration)
4. **Geographic expansion** — duplicate agency+property setup for new cities
5. **Analytics dashboard** — Power BI connected to `/stats` endpoint
