-- FixZA — Supabase/PostgreSQL schema
-- Run in Supabase SQL Editor. Mirrors app/models.py (SQLAlchemy creates the
-- same tables automatically, but this file is the canonical production schema).

create table if not exists customers (
    id          bigint generated always as identity primary key,
    wa_id       varchar(32) not null unique,
    name        varchar(120) not null default '',
    created_at  timestamptz not null default now()
);

create table if not exists artisans (
    id                bigint generated always as identity primary key,
    wa_id             varchar(32) not null unique,
    name              varchar(120) not null,
    trade             varchar(40) not null,
    suburb            varchar(80) not null default '',
    lat               double precision not null,
    lng               double precision not null,
    verification_tier varchar(10) not null default 'bronze'
                      check (verification_tier in ('bronze','silver','gold')),
    rating            double precision not null default 0,
    jobs_completed    integer not null default 0,
    declines          integer not null default 0,
    no_shows          integer not null default 0,
    active            integer not null default 1,
    created_at        timestamptz not null default now()
);
create index if not exists idx_artisans_trade on artisans (trade) where active = 1;

create table if not exists agencies (
    id            bigint generated always as identity primary key,
    name          varchar(120) not null,
    contact_wa_id varchar(32) not null default '',
    created_at    timestamptz not null default now()
);

create table if not exists properties (
    id         bigint generated always as identity primary key,
    agency_id  bigint not null references agencies(id),
    label      varchar(160) not null,
    suburb     varchar(80) not null default '',
    lat        double precision not null,
    lng        double precision not null
);
create index if not exists idx_properties_agency on properties (agency_id);

create table if not exists tenants (
    id          bigint generated always as identity primary key,
    wa_id       varchar(32) not null unique,
    name        varchar(120) not null default '',
    property_id bigint not null references properties(id)
);

create table if not exists recurring_schedules (
    id              bigint generated always as identity primary key,
    property_id     bigint not null references properties(id),
    trade           varchar(40) not null,
    description     text not null,
    frequency_days  integer not null,
    next_due_at     timestamptz not null,
    active          integer not null default 1,
    created_at      timestamptz not null default now()
);
create index if not exists idx_schedules_property on recurring_schedules (property_id);

create table if not exists jobs (
    id           bigint generated always as identity primary key,
    customer_id  bigint not null references customers(id),
    artisan_id   bigint references artisans(id),
    property_id  bigint references properties(id),
    agency_id    bigint references agencies(id),
    description  text not null,
    trade        varchar(40) not null,
    urgency      varchar(10) not null default 'normal',
    lat          double precision,
    lng          double precision,
    suburb       varchar(80) not null default '',
    status       varchar(15) not null default 'draft'
                 check (status in ('draft','matched','booked','completed','cancelled')),
    sla_due_at   timestamptz,
    created_at   timestamptz not null default now()
);
create index if not exists idx_jobs_agency on jobs (agency_id);
create index if not exists idx_jobs_customer on jobs (customer_id);
create index if not exists idx_jobs_status   on jobs (status);
create index if not exists idx_jobs_trade    on jobs (trade);

create table if not exists quotes (
    id          bigint generated always as identity primary key,
    job_id      bigint not null references jobs(id),
    artisan_id  bigint not null references artisans(id),
    amount_zar  double precision not null,
    note        text not null default '',
    status      varchar(10) not null default 'pending'
                check (status in ('pending','accepted','rejected')),
    created_at  timestamptz not null default now()
);
create index if not exists idx_quotes_job on quotes (job_id);

create table if not exists reviews (
    id          bigint generated always as identity primary key,
    job_id      bigint not null unique references jobs(id),
    artisan_id  bigint not null references artisans(id),
    stars       integer not null check (stars between 1 and 5),
    comment     text not null default '',
    created_at  timestamptz not null default now()
);
create index if not exists idx_reviews_artisan on reviews (artisan_id);

create table if not exists sessions (
    wa_id            varchar(32) primary key,
    state            varchar(30) not null default 'new',
    pending_job_id   bigint,
    offered_artisans varchar(60) not null default '',
    updated_at       timestamptz not null default now()
);

create table if not exists message_log (
    id          bigint generated always as identity primary key,
    wa_id       varchar(32) not null,
    direction   varchar(3) not null check (direction in ('in','out')),
    body        text not null,
    created_at  timestamptz not null default now()
);
create index if not exists idx_msglog_wa on message_log (wa_id);

-- POPIA: retention — purge raw message bodies older than 90 days (schedule
-- via Supabase pg_cron or a Render cron job):
--   delete from message_log where created_at < now() - interval '90 days';
