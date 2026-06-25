/**
 * SendGrid Event Webhook → GitHub repository_dispatch bridge
 *
 * SendGrid calls this endpoint with an array of email events.
 * We filter for email_open and click events, then trigger the
 * scoring agent via GitHub repository_dispatch.
 *
 * Required Supabase secrets:
 *   SENDGRID_WEBHOOK_PUBLIC_KEY  — ECDSA public key from SendGrid settings
 *   GITHUB_PAT                   — classic PAT with repo scope
 *   GITHUB_REPO_OWNER            — garrettc123
 *   GITHUB_REPO_NAME             — garcar-control-plane
 */

import { serve } from 'https://deno.land/std@0.177.0/http/server.ts'

const GITHUB_OWNER = Deno.env.get('GITHUB_REPO_OWNER') ?? 'garrettc123'
const GITHUB_REPO  = Deno.env.get('GITHUB_REPO_NAME')  ?? 'garcar-control-plane'
const GITHUB_PAT   = Deno.env.get('GITHUB_PAT') ?? ''

type SendGridEvent = {
  event: string
  email: string
  timestamp: number
  'smtp-id'?: string
  sg_event_id?: string
  sg_message_id?: string
  url?: string
  // custom args we attach at send time
  lead_id?: string
  batch_id?: string
  sequence_day?: string
}

async function dispatchToGitHub(eventType: string, payload: Record<string, unknown>): Promise<void> {
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/dispatches`
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `token ${GITHUB_PAT}`,
      'Accept': 'application/vnd.github.v3+json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      event_type: eventType,
      client_payload: payload,
    }),
  })

  if (!resp.ok) {
    const body = await resp.text()
    throw new Error(`GitHub dispatch failed: ${resp.status} ${body}`)
  }
}

serve(async (req: Request) => {
  if (req.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 })
  }

  let events: SendGridEvent[]
  try {
    events = await req.json()
  } catch {
    return new Response('Invalid JSON', { status: 400 })
  }

  const dispatched: string[] = []
  const errors: string[] = []

  for (const ev of events) {
    const lead_id    = ev.lead_id ?? ''
    const batch_id   = ev.batch_id ?? ''
    const email      = ev.email ?? ''
    const seq_day    = ev.sequence_day ?? '0'

    try {
      if (ev.event === 'open') {
        await dispatchToGitHub('sendgrid_email_opened', {
          lead_id,
          batch_id,
          email,
          sequence_day: seq_day,
          sg_event_id: ev.sg_event_id,
          timestamp: ev.timestamp,
        })
        dispatched.push(`open:${email}`)
      } else if (ev.event === 'click') {
        await dispatchToGitHub('sendgrid_link_clicked', {
          lead_id,
          batch_id,
          email,
          url: ev.url,
          sequence_day: seq_day,
          sg_event_id: ev.sg_event_id,
          timestamp: ev.timestamp,
        })
        dispatched.push(`click:${email}`)
      }
      // bounce/spam/unsubscribe — mark lead as suppressed in Supabase
      else if (['bounce', 'spamreport', 'unsubscribe'].includes(ev.event)) {
        await dispatchToGitHub('sendgrid_suppressed', {
          lead_id,
          batch_id,
          email,
          reason: ev.event,
          timestamp: ev.timestamp,
        })
        dispatched.push(`suppressed:${email}`)
      }
    } catch (err) {
      errors.push(`${ev.event}:${email} — ${(err as Error).message}`)
    }
  }

  console.log(`[sendgrid-webhook] dispatched=${dispatched.length} errors=${errors.length}`)
  if (errors.length) console.error('[sendgrid-webhook] errors:', errors)

  return new Response(
    JSON.stringify({ ok: true, dispatched: dispatched.length, errors }),
    { headers: { 'Content-Type': 'application/json' } }
  )
})
