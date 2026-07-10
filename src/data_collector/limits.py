"""Server-side maxima applied to every evidence request before dispatch.

No request may reach an MCP with an unbounded lookback, row count, timeout, or
logging limit. ``enforce`` clamps the offending parameters and returns the
values actually used, which the collector records as the request's provenance.
"""

import typing

from data_collector import models

DEFAULT_LOGGING_LIMIT = 100
MAX_LOGGING_LIMIT = 500
MAX_LOOKBACK_SECONDS = 7 * 24 * 60 * 60
MAX_ROWS = 500
MAX_TIMEOUT_MS = 30_000

Params = typing.Mapping[str, typing.Any]


def enforce(source: models.Source, params: Params) -> dict[str, typing.Any]:
    """Returns ``params`` with server-side maxima applied before dispatch."""
    applied = dict(params)

    if source is models.Source.LOGGING:
        requested = applied.get("limit", DEFAULT_LOGGING_LIMIT)
        applied["limit"] = min(requested, MAX_LOGGING_LIMIT)

    if "lookback_seconds" in applied:
        applied["lookback_seconds"] = min(
            applied["lookback_seconds"], MAX_LOOKBACK_SECONDS
        )
    if "rows" in applied:
        applied["rows"] = min(applied["rows"], MAX_ROWS)
    if "timeout_ms" in applied:
        applied["timeout_ms"] = min(applied["timeout_ms"], MAX_TIMEOUT_MS)

    return applied
