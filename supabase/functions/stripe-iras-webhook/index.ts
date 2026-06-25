/**
 * Stripe Webhook → GitHub repository_dispatch bridge
 *
 * Receives Stripe events, verifies HMAC signature,
 * then fires the appropriate IRAS pipeline step.
 *
 * Required Supabase secrets:
 *   STRIPE_WEBHOOK_SECRET   — from Stripe Dashboard → Webhooks
 *   GITHUB_PAT              — classic PAT with repo scope
 *   GITHUB_REPO_OWNER       — garrettc123
 *   GITHUB_REPO_NAME        — garcar-control-plane
 */

import { serve } from 'https://deno.land/std@0.177.0/http/server.ts'
import Stripe from 'https://esm.sh/stripe@14.21.0?target=deno'

const stripe = new Stripe(Deno.env.get('STRIPE_SECRET_KEY') ?? '', {
  apiVersion: '2024-06-20',
  httpClient: Stripe.createFetchHttpClient(),
})

const WEBHOOK_SECRET  = Deno.env.get('STRIPE_WEBHOOK_SECRET') ?? ''
const GITHUB_PAT      = Deno.env.get('GITHUB_PAT') ?? ''
const GITHUB_OWNER    = Deno.env.get('GITHUB_REPO_OWNER') ?? 'garrettc123'
const GITHUB_REPO     = Deno.env.get('GITHUB_REPO_NAME')  ?? 'garcar-control-plane'

async function dispatchToGitHub(eventType: string, payload: Record<string, unknown>): Promise<void> {
  const resp = await fetch(
    `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/dispatches`,
    {
      method: 'POST',
      headers: {
        'Authorization': `token ${GITHUB_PAT}`,
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ event_type: eventType, client_payload: payload }),
    }
  )
  if (!resp.ok) {
    const body = await resp.text()
    throw new Error(`GitHub dispatch failed ${resp.status}: ${body}`)
  }
}

serve(async (req: Request) => {
  if (req.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 })
  }

  const sig = req.headers.get('stripe-signature') ?? ''
  const body = await req.text()

  let event: Stripe.Event
  try {
    event = await stripe.webhooks.constructEventAsync(body, sig, WEBHOOK_SECRET)
  } catch (err) {
    console.error('[stripe-iras-webhook] Signature verification failed:', err)
    return new Response(`Webhook signature verification failed`, { status: 400 })
  }

  console.log(`[stripe-iras-webhook] Received: ${event.type}`)

  try {
    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object as Stripe.Checkout.Session
        await dispatchToGitHub('stripe_checkout_completed', {
          stripe_customer_id: session.customer as string,
          session_id: session.id,
          lead_id: session.metadata?.lead_id ?? '',
          product_id: session.metadata?.product_id ?? 'garcar-starter-500',
          amount_total: session.amount_total,
          currency: session.currency,
        })
        break
      }

      case 'payment_intent.succeeded': {
        const pi = event.data.object as Stripe.PaymentIntent
        await dispatchToGitHub('stripe_payment_succeeded', {
          stripe_customer_id: pi.customer as string,
          payment_intent_id: pi.id,
          lead_id: pi.metadata?.lead_id ?? '',
          product_id: pi.metadata?.product_id ?? '',
          amount: pi.amount,
          currency: pi.currency,
        })
        break
      }

      case 'invoice.payment_succeeded': {
        const invoice = event.data.object as Stripe.Invoice
        // Recurring subscription payment — log but don't re-onboard
        console.log(`[stripe-iras-webhook] Recurring payment: customer=${invoice.customer} amount=${invoice.amount_paid}`)
        break
      }

      case 'customer.subscription.deleted': {
        const sub = event.data.object as Stripe.Subscription
        await dispatchToGitHub('stripe_subscription_cancelled', {
          stripe_customer_id: sub.customer as string,
          subscription_id: sub.id,
          cancelled_at: sub.canceled_at,
        })
        break
      }

      default:
        console.log(`[stripe-iras-webhook] Unhandled event type: ${event.type}`)
    }
  } catch (err) {
    console.error('[stripe-iras-webhook] Dispatch error:', err)
    return new Response('Dispatch failed', { status: 500 })
  }

  return new Response(JSON.stringify({ received: true, type: event.type }), {
    headers: { 'Content-Type': 'application/json' },
  })
})
