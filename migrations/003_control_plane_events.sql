-- control_plane_events: records every payment_processed dispatch received
-- from garcar-payment-loop. Separate from gc_ledger (which records the
-- full sync_wealth_loop outcome) — this table is the control-plane's own
-- event log for the cognitive engine.

create table if not exists control_plane_events (
  id                bigserial primary key,
  created_at        timestamptz not null default now(),
  trace_id          text,
  stripe_event_id   text unique,
  stripe_event_type text,
  customer_email    text,
  amount_total      bigint,
  source            text not null default 'garcar-payment-loop',
  stage             text not null default 'payment_processed'
);

create index if not exists control_plane_events_created_at
  on control_plane_events (created_at desc);

create index if not exists control_plane_events_trace_id
  on control_plane_events (trace_id)
  where trace_id is not null;

alter table control_plane_events enable row level security;

create policy "service_role_all" on control_plane_events
  for all using (auth.role() = 'service_role');
