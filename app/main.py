"""FixZA — WhatsApp artisan marketplace API.

Endpoints:
  GET  /webhook   Meta webhook verification handshake
  POST /webhook   Inbound WhatsApp messages (signature-verified)
  GET  /health    Liveness probe (Render)
  GET  /stats     Simple ops metrics (feed for Power BI / dashboards)
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .conversation import handle_message
from .db import get_db, init_db
from .models import Agency, Artisan, Customer, Job, MessageLog, utcnow
from .whatsapp import extract_messages, send_text, verify_signature

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("fixza")

app = FastAPI(title="FixZA API", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    init_db()
    if config.DRY_RUN:
        log.warning("Running in DRY-RUN mode: outbound WhatsApp messages are logged, not sent.")


@app.get("/", include_in_schema=False)
def landing() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "dry_run": config.DRY_RUN}


@app.get("/webhook")
def verify_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """Meta calls this once when you configure the webhook URL."""
    if hub_mode == "subscribe" and hub_verify_token == config.WHATSAPP_VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    raw = await request.body()
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=403, detail="Bad signature")

    body = await request.json()
    for msg in extract_messages(body):
        try:
            db.add(MessageLog(wa_id=msg["wa_id"], direction="in",
                              body=msg.get("text") or f"[{msg['type']}]"))
            replies = handle_message(db, msg)
            db.commit()
        except Exception:
            db.rollback()
            log.exception("Failed handling message from %s", msg.get("wa_id"))
            replies = ["Eish, something went wrong on our side. Please try again. 🙏"]
        for reply in replies:
            db.add(MessageLog(wa_id=msg["wa_id"], direction="out", body=reply))
            await send_text(msg["wa_id"], reply)
        db.commit()
    # Always 200 so Meta doesn't retry-storm us.
    return {"status": "received"}


def _job_row(job: Job) -> dict:
    overdue = bool(
        job.sla_due_at
        and job.status in ("draft", "matched")
        and job.sla_due_at.replace(tzinfo=None) < utcnow().replace(tzinfo=None)
    )
    return {
        "ref": f"FZ-{job.id:05d}",
        "property": job.property.label if job.property else "",
        "suburb": job.suburb,
        "trade": job.trade,
        "urgency": job.urgency,
        "status": job.status,
        "artisan": job.artisan.name if job.artisan else None,
        "sla_due_at": job.sla_due_at.isoformat() if job.sla_due_at else None,
        "sla_overdue": overdue,
        "created_at": job.created_at.isoformat(),
    }


@app.get("/agency/{agency_id}/jobs")
def agency_jobs(agency_id: int, db: Session = Depends(get_db)) -> dict:
    agency = db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(404, "Agency not found")
    jobs = db.scalars(
        select(Job).where(Job.agency_id == agency_id).order_by(Job.id.desc())
    ).all()
    return {"agency": agency.name, "jobs": [_job_row(j) for j in jobs]}


@app.get("/agency/{agency_id}", response_class=HTMLResponse, include_in_schema=False)
def agency_dashboard(agency_id: int, db: Session = Depends(get_db)) -> str:
    agency = db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(404, "Agency not found")
    jobs = db.scalars(
        select(Job).where(Job.agency_id == agency_id).order_by(Job.id.desc())
    ).all()
    rows = [_job_row(j) for j in jobs]
    open_jobs = sum(1 for r in rows if r["status"] in ("draft", "matched", "booked"))
    overdue = sum(1 for r in rows if r["sla_overdue"])
    urgency_dot = {"urgent": "🔴", "normal": "🟢"}
    body_rows = "".join(
        f"<tr><td>{r['ref']}</td><td>{r['property']}</td><td>{r['trade']}</td>"
        f"<td>{urgency_dot.get(r['urgency'], '')} {r['urgency']}</td>"
        f"<td><span class='pill {r['status']}'>{r['status']}</span></td>"
        f"<td>{r['artisan'] or '—'}</td>"
        f"<td class='{'over' if r['sla_overdue'] else ''}'>"
        f"{(r['sla_due_at'] or '')[:16].replace('T', ' ')}"
        f"{' ⚠ OVERDUE' if r['sla_overdue'] else ''}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='7'>No jobs yet — tenants just WhatsApp FixZA.</td></tr>"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{agency.name} — FixZA dashboard</title>
<style>
 body{{font-family:'Segoe UI',sans-serif;background:#faf5ec;color:#2b1d12;margin:0}}
 header{{background:linear-gradient(135deg,#c2410c,#e6a817);color:#fff;padding:26px 36px}}
 header h1{{margin:0;font-size:1.5rem}} header p{{margin:4px 0 0;opacity:.9}}
 .cards{{display:flex;gap:16px;padding:24px 36px 0}}
 .card{{background:#fff;border-radius:14px;padding:18px 26px;box-shadow:0 4px 14px rgba(120,60,10,.08)}}
 .card b{{font-size:1.7rem;color:#c2410c;display:block}}
 table{{width:calc(100% - 72px);margin:24px 36px;border-collapse:collapse;background:#fff;
   border-radius:14px;overflow:hidden;box-shadow:0 4px 14px rgba(120,60,10,.08)}}
 th,td{{padding:11px 14px;text-align:left;font-size:.9rem;border-bottom:1px solid #f0e6d4}}
 th{{background:#2b1d12;color:#fff;font-weight:600}}
 .pill{{padding:3px 10px;border-radius:99px;font-size:.75rem;font-weight:600}}
 .pill.booked{{background:#dcfce7;color:#166534}} .pill.matched{{background:#fef9c3;color:#854d0e}}
 .pill.completed{{background:#e0e7ff;color:#3730a3}} .pill.cancelled{{background:#fee2e2;color:#991b1b}}
 .pill.draft{{background:#f3f4f6;color:#374151}} .over{{color:#b91c1c;font-weight:700}}
</style></head><body>
<header><h1>🔧 {agency.name} — maintenance dashboard</h1>
<p>Powered by FixZA · tenants report via WhatsApp, you watch it here</p></header>
<div class="cards">
 <div class="card"><b>{len(rows)}</b>total jobs</div>
 <div class="card"><b>{open_jobs}</b>open</div>
 <div class="card"><b>{overdue}</b>SLA overdue</div>
</div>
<table><tr><th>Ref</th><th>Property</th><th>Trade</th><th>Urgency</th>
<th>Status</th><th>Artisan</th><th>Response due (SLA)</th></tr>{body_rows}</table>
</body></html>"""


@app.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    """Operational metrics — point Power BI (web connector) at this endpoint."""
    jobs_by_status = dict(
        db.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    )
    return {
        "customers": db.scalar(select(func.count(Customer.id))),
        "artisans": db.scalar(select(func.count(Artisan.id))),
        "jobs_by_status": jobs_by_status,
        "jobs_by_trade": dict(
            db.execute(select(Job.trade, func.count()).group_by(Job.trade)).all()
        ),
    }
