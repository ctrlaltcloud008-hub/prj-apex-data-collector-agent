"""The deterministic evidence collector application entrypoint."""

import asyncio
import datetime
import time
import typing

from data_collector import limits, models, ports, routing

DEFAULT_BACKGROUND_CONCURRENCY = 8


async def _collect_one(
    request: models.EvidenceRequest,
    clients: typing.Mapping[models.Source, ports.McpClient],
) -> models.EvidenceResult:
    """Routes and executes a single evidence request."""
    # A source is available only when it is both wired (its MCP exists) and a
    # healthy client is present. A missing client models an unhealthy or
    # not-yet-started MCP subprocess and degrades cleanly rather than crashing.
    if not routing.is_available(request.source) or (
        request.source not in clients
    ):
        return _failed(
            request,
            tool=None,
            error=models.EvidenceError(
                code="source_unavailable",
                message=f"Source '{request.source.value}' is unavailable",
                retryable=True,
            ),
            duration_ms=0,
        )
    tool = routing.route(request.source, request.query_type, request.params)
    if tool is None:
        return _failed(
            request,
            tool=None,
            error=models.EvidenceError(
                code="validation_error",
                message=(
                    f"No route for source '{request.source.value}' and "
                    f"query_type '{request.query_type}'"
                ),
                retryable=False,
            ),
            duration_ms=0,
        )
    params_used = limits.enforce(request.source, request.params)
    started = time.monotonic()
    client = clients[request.source]
    try:
        result = await client.call_tool(tool, params_used)
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return _failed(request, tool, _classify(exc), duration_ms)
    duration_ms = int((time.monotonic() - started) * 1000)
    return models.EvidenceResult(
        request_id=request.request_id,
        source=request.source,
        tool_called=tool,
        params_used=params_used,
        record_count=result.record_count,
        data=result.data,
        collected_at=datetime.datetime.now(datetime.UTC),
        duration_ms=duration_ms,
        error=None,
    )


def _classify(exc: Exception) -> models.EvidenceError:
    """Maps an MCP failure to a typed, retryable-aware evidence error.

    Transport and timeout failures are transient and safe to retry; anything
    else is treated as a permanent error the same request would hit again.
    """
    if isinstance(exc, TimeoutError):
        return models.EvidenceError(
            code="timeout", message=str(exc), retryable=True
        )
    if isinstance(exc, ConnectionError):
        return models.EvidenceError(
            code="transport_error", message=str(exc), retryable=True
        )
    return models.EvidenceError(
        code="mcp_error", message=str(exc), retryable=False
    )


def _failed(
    request: models.EvidenceRequest,
    tool: str | None,
    error: models.EvidenceError,
    duration_ms: int,
) -> models.EvidenceResult:
    """Builds a provenance-tagged result carrying a per-request error."""
    return models.EvidenceResult(
        request_id=request.request_id,
        source=request.source,
        tool_called=tool,
        params_used=request.params,
        record_count=0,
        data=None,
        collected_at=datetime.datetime.now(datetime.UTC),
        duration_ms=duration_ms,
        error=error,
    )


async def collect_stream(
    request: models.CollectRequest,
    clients: typing.Mapping[models.Source, ports.McpClient],
    sink: ports.TelemetrySink | None = None,
    background_concurrency: int = DEFAULT_BACKGROUND_CONCURRENCY,
) -> typing.AsyncIterator[models.EvidenceResult]:
    """Yields evidence results as they complete, blocking requests first.

    Blocking requests are dispatched immediately and concurrently; background
    requests run concurrently under ``background_concurrency``. All blocking
    results are yielded before any background result, so a slow background read
    never delays a completed blocking read.
    """
    semaphore = asyncio.Semaphore(background_concurrency)

    async def _run(evidence: models.EvidenceRequest) -> models.EvidenceResult:
        return await _collect_one(evidence, clients)

    async def _run_bounded(
        evidence: models.EvidenceRequest,
    ) -> models.EvidenceResult:
        async with semaphore:
            return await _collect_one(evidence, clients)

    blocking = [
        asyncio.ensure_future(_run(evidence))
        for evidence in request.requests
        if evidence.priority is models.Priority.BLOCKING
    ]
    background = [
        asyncio.ensure_future(_run_bounded(evidence))
        for evidence in request.requests
        if evidence.priority is models.Priority.BACKGROUND
    ]

    for task in (*_as_completed(blocking), *_as_completed(background)):
        result = await task
        if sink is not None:
            await sink.emit(_telemetry(request.investigation_id, result))
        yield result


def _as_completed(
    tasks: list[asyncio.Future[models.EvidenceResult]],
) -> typing.Iterator[asyncio.Future[models.EvidenceResult]]:
    """Wraps ``asyncio.as_completed`` for a typed list of result futures."""
    return iter(asyncio.as_completed(tasks)) if tasks else iter(())


async def collect(
    request: models.CollectRequest,
    clients: typing.Mapping[models.Source, ports.McpClient],
    sink: ports.TelemetrySink | None = None,
    background_concurrency: int = DEFAULT_BACKGROUND_CONCURRENCY,
) -> models.CollectResponse:
    """Collects every requested evidence item for one Investigation.

    The batch response preserves request order; use ``collect_stream`` to
    observe results progressively as they complete.
    """
    by_id: dict[str, models.EvidenceResult] = {}
    async for result in collect_stream(
        request, clients, sink, background_concurrency
    ):
        by_id[result.request_id] = result
    ordered = tuple(by_id[evidence.request_id] for evidence in request.requests)
    return models.CollectResponse(
        investigation_id=request.investigation_id,
        results=ordered,
    )


def _telemetry(
    investigation_id: str, result: models.EvidenceResult
) -> models.ToolCallTelemetry:
    """Derives one telemetry record from a completed evidence result."""
    outcome = "success" if result.error is None else result.error.code
    return models.ToolCallTelemetry(
        investigation_id=investigation_id,
        request_id=result.request_id,
        source=result.source,
        tool_called=result.tool_called,
        record_count=result.record_count,
        duration_ms=result.duration_ms,
        outcome=outcome,
    )
