# Checkout Service

## Overview

checkout-service owns the cart-to-order flow. It receives `POST /checkout`
from the frontend, validates the cart contents, creates an order record,
and hands off to payments-service and inventory-service to finish the
purchase. It is the most user-facing service in the stack: any elevated
error rate here shows up immediately as failed purchases.

## Dependencies

- payments-service (synchronous call, blocks the checkout response)
- inventory-service (synchronous call, blocks the checkout response)
- shipping-rate-carrier (external, synchronous call, blocks the checkout response)
- Postgres `orders` table

## Normal operating range

- error rate: under 2%
- p50 latency: ~110ms
- request volume: 30-70 requests per tick under normal simulated load

Anything sustained above 5% error rate should be treated as an active
incident, not noise.

## Known issues

### Missing shipping_method field causes 500s

Symptom: `500 Internal Server Error handling POST /checkout: KeyError:
'shipping_method'`, sometimes surfacing instead as `OrderCreationError:
missing required field shipping_method for order {order_id}` or
`Unhandled exception in checkout flow: 'shipping_method' not found in
request body`.

Root cause: a deploy changed the checkout request schema to require a
`shipping_method` field but didn't add a default or backward-compatible
fallback for clients still sending the old request shape. Every request
missing the field throws a KeyError deep in order creation.

This is the single most common incident on this service. If you see this
exact error signature, check deploy history for a recent change to the
checkout request schema or order creation code before looking anywhere
else. The fix is almost always either rolling back that deploy or shipping
a hotfix that defaults `shipping_method` when absent.

### Slow shipping-rate carrier

Symptom: `Timeout calling shipping-rate-carrier after 8000ms for order
{order_id}`, `Slow response from shipping-rate-carrier: 6500ms for order
{order_id}`, or `CheckoutLatencyWarning: shipping rate lookup exceeded
SLA for order {order_id}`. Latency climbs sharply, often five times
normal, while the error rate only moves a little, most requests still
eventually succeed, just slowly.

Root cause: the shipping-rate carrier checkout calls out to for live
shipping quotes has gotten slow on their end. This is not caused by a
deploy here, nothing in checkout-service's own code or config changed.
Check deploy history anyway to rule it out, but expect to find nothing
recent.

There's no fix on our side beyond waiting it out or, if it's prolonged,
falling back to cached/flat-rate shipping estimates instead of a live
carrier lookup.

### Elevated latency without elevated errors

If latency climbs but the error rate stays flat or only moves a little,
suspect payments-service, inventory-service, or the shipping-rate
carrier rather than checkout-service itself, since all three downstream
calls are synchronous and block the checkout response. Check their
metrics (and, for the carrier, the known issue above) before assuming
the problem is here.

## Escalation

If error rate stays above 20% for more than a few minutes and the cause
isn't obvious from deploy history, treat it as customer-impacting and
escalate immediately. Checkout failures directly block revenue.
