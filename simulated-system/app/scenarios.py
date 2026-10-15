from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    service: str
    description: str
    error_rate: float
    latency_multiplier: float
    error_log_messages: list[str]
    deploy_message: str | None


SCENARIOS: dict[str, Scenario] = {
    "checkout-500s": Scenario(
        id="checkout-500s",
        title="Checkout returning 500s",
        service="checkout-service",
        description=(
            "A bad deploy ships without validating the new shipping_method field, "
            "so any checkout request missing it blows up with a 500."
        ),
        error_rate=0.35,
        latency_multiplier=1.1,
        error_log_messages=[
            "500 Internal Server Error handling POST /checkout: KeyError: 'shipping_method'",
            "Unhandled exception in checkout flow: 'shipping_method' not found in request body",
            "OrderCreationError: missing required field shipping_method for order {order_id}",
        ],
        deploy_message="Add shipping method to checkout request schema",
    ),
    "payments-timeout": Scenario(
        id="payments-timeout",
        title="Payments provider timing out",
        service="payments-service",
        description=(
            "A connection pool size change leaves payments-service unable to keep up "
            "with the payment provider, so a growing share of requests time out."
        ),
        error_rate=0.22,
        latency_multiplier=4.5,
        error_log_messages=[
            "Timeout calling payment-provider after 30000ms for charge {order_id}",
            "ConnectionPoolExhausted: no available connections to payment-provider",
            "Retry limit exceeded charging card for order {order_id}, giving up",
        ],
        deploy_message="Reduce payment-provider connection pool size",
    ),
    "inventory-oom": Scenario(
        id="inventory-oom",
        title="Inventory service getting OOM killed",
        service="inventory-service",
        description=(
            "A memory leak introduced in the stock-reservation cache causes the "
            "process to slowly grow until it gets killed and restarted under load."
        ),
        error_rate=0.18,
        latency_multiplier=1.6,
        error_log_messages=[
            "OOMKilled: inventory-worker exceeded memory limit (512Mi)",
            "Process restarted unexpectedly while reserving stock for order {order_id}",
            "Failed to reserve inventory for order {order_id}: worker unavailable",
        ],
        deploy_message="Cache stock-reservation lookups in memory",
    ),
    "checkout-slow-carrier": Scenario(
        id="checkout-slow-carrier",
        title="Checkout latency spike from a slow shipping carrier",
        service="checkout-service",
        description=(
            "The shipping-rate carrier checkout calls out to synchronously has gotten "
            "slow, so checkout latency climbs sharply while the error rate barely moves. "
            "Not a deploy, no code here changed."
        ),
        error_rate=0.06,
        latency_multiplier=5.0,
        error_log_messages=[
            "Timeout calling shipping-rate-carrier after 8000ms for order {order_id}",
            "Slow response from shipping-rate-carrier: 6500ms for order {order_id}",
            "CheckoutLatencyWarning: shipping rate lookup exceeded SLA for order {order_id}",
        ],
        deploy_message=None,
    ),
    "payments-bad-credentials": Scenario(
        id="payments-bad-credentials",
        title="Payments provider rejecting every request",
        service="payments-service",
        description=(
            "A rotated API credential was never updated in payments-service's config, "
            "so the payment provider rejects nearly every request outright. Requests "
            "fail fast rather than hang, latency stays close to normal."
        ),
        error_rate=0.9,
        latency_multiplier=1.2,
        error_log_messages=[
            "401 Unauthorized calling payment-provider for charge {order_id}: invalid API credentials",
            "AuthenticationError: payment-provider rejected request, check API key configuration",
            "Payment provider returned invalid_api_key for order {order_id}",
        ],
        deploy_message=None,
    ),
    "inventory-db-lock": Scenario(
        id="inventory-db-lock",
        title="Inventory reservations stuck on database lock contention",
        service="inventory-service",
        description=(
            "A long-running reporting query is holding row locks on the inventory "
            "table, so checkout-time stock reservations queue up waiting for locks "
            "and start timing out. Not a deploy, no recent code change caused this."
        ),
        error_rate=0.25,
        latency_multiplier=6.0,
        error_log_messages=[
            "Lock wait timeout exceeded for inventory reservation on order {order_id}",
            "DeadlockDetected: inventory row lock held too long, retrying order {order_id}",
            "Database query timeout (30000ms) reserving stock for order {order_id}",
        ],
        deploy_message=None,
    ),
}
