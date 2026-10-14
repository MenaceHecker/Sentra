"""Phase 10: one shared Limiter instance so every route's @limiter.limit(...)
decorator and the app-level SlowAPIMiddleware (wired up in main.py) count
against the same counters. Keyed by IP, not by user, so login and register
(no authenticated user yet) are covered by the same scheme as everything
else rather than needing a separate rule.

key_style="endpoint" matters here specifically: slowapi's default,
"url", scopes each limit by the exact resolved request path, including
path parameters. For a route like POST /{incident_id}/investigate that
means every distinct incident_id would get its own counter, so hitting
the same route repeatedly against different incidents would never
actually trip the limit. "endpoint" scopes by the route's view function
instead, which is what "N requests to this route per minute" should mean.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, key_style="endpoint")
