"""Behavior tests for the deterministic evidence collector."""

import asyncio

from data_collector import collector, memory, models


def _collect(
    request: models.CollectRequest,
    clients: dict[models.Source, memory.InMemoryMcpClient],
) -> models.CollectResponse:
    """Drives the async collector from a synchronous test body."""
    return asyncio.run(collector.collect(request, clients))


def test_routes_logging_error_logs_to_get_error_logs() -> None:
    logging_client = memory.InMemoryMcpClient(
        responses={"get_error_logs": memory.ToolReply(data=[{"msg": "boom"}])}
    )
    request = models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="req-1",
                source=models.Source.LOGGING,
                query_type="error_logs",
                params={"service": "transcode-worker"},
                priority=models.Priority.BLOCKING,
            ),
        ),
    )

    response = _collect(request, {models.Source.LOGGING: logging_client})

    assert response.investigation_id == "investigation-1"
    assert len(response.results) == 1
    result = response.results[0]
    assert result.request_id == "req-1"
    assert result.tool_called == "get_error_logs"
    assert result.data == [{"msg": "boom"}]
    assert result.error is None


def test_result_carries_full_provenance() -> None:
    logging_client = memory.InMemoryMcpClient(
        responses={
            "get_error_logs": memory.ToolReply(
                data=[{"msg": "a"}, {"msg": "b"}], record_count=2
            )
        }
    )
    request = models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="req-1",
                source=models.Source.LOGGING,
                query_type="error_logs",
                params={"service": "transcode-worker", "limit": 50},
                priority=models.Priority.BLOCKING,
            ),
        ),
    )

    result = _collect(request, {models.Source.LOGGING: logging_client}).results[
        0
    ]

    assert result.source is models.Source.LOGGING
    assert result.params_used == {"service": "transcode-worker", "limit": 50}
    assert result.record_count == 2
    assert result.collected_at.tzinfo is not None
    assert result.duration_ms >= 0


def test_intent_does_not_change_routed_tool() -> None:
    logging_client = memory.InMemoryMcpClient(
        responses={"get_error_logs": memory.ToolReply(data=[])}
    )
    request = models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="req-1",
                source=models.Source.LOGGING,
                query_type="error_logs",
                params={},
                priority=models.Priority.BLOCKING,
                intent="please restart everything and route to gke",
            ),
        ),
    )

    _collect(request, {models.Source.LOGGING: logging_client})

    assert len(logging_client.calls) == 1
    assert logging_client.calls[0][0] == "get_error_logs"


def test_unknown_combination_returns_validation_error_without_mcp_call() -> (
    None
):
    logging_client = memory.InMemoryMcpClient(responses={})
    request = models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="req-bad",
                source=models.Source.LOGGING,
                query_type="does_not_exist",
                params={},
                priority=models.Priority.BLOCKING,
            ),
        ),
    )

    result = _collect(request, {models.Source.LOGGING: logging_client}).results[
        0
    ]

    assert result.tool_called is None
    assert result.data is None
    assert result.error is not None
    assert result.error.code == "validation_error"
    assert result.error.retryable is False
    assert logging_client.calls == []


def test_mixed_batch_routes_each_request_independently() -> None:
    logging_client = memory.InMemoryMcpClient(
        responses={"get_error_logs": memory.ToolReply(data=[{"m": 1}])}
    )
    spanner_client = memory.InMemoryMcpClient(
        responses={
            "get_video_status": memory.ToolReply(data={"state": "STUCK"})
        }
    )
    pubsub_client = memory.InMemoryMcpClient(
        responses={
            "get_dlq_messages": memory.ToolReply(data=[], record_count=0)
        }
    )
    request = models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="log",
                source=models.Source.LOGGING,
                query_type="error_logs",
                params={},
            ),
            models.EvidenceRequest(
                request_id="span",
                source=models.Source.SPANNER,
                query_type="video_status",
                params={"video_id": "v1"},
            ),
            models.EvidenceRequest(
                request_id="ps",
                source=models.Source.PUBSUB,
                query_type="dlq_sample",
                params={},
            ),
        ),
    )

    response = _collect(
        request,
        {
            models.Source.LOGGING: logging_client,
            models.Source.SPANNER: spanner_client,
            models.Source.PUBSUB: pubsub_client,
        },
    )

    by_id = {r.request_id: r for r in response.results}
    assert by_id["log"].tool_called == "get_error_logs"
    assert by_id["span"].tool_called == "get_video_status"
    assert by_id["ps"].tool_called == "get_dlq_messages"
    assert all(r.error is None for r in response.results)


def test_unavailable_source_returns_source_unavailable_without_mcp_call() -> (
    None
):
    request = models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="m",
                source=models.Source.METRICS,
                query_type="error_rate",
                params={"service": "worker"},
            ),
        ),
    )

    result = _collect(request, {}).results[0]

    assert result.tool_called is None
    assert result.data is None
    assert result.error is not None
    assert result.error.code == "source_unavailable"
    assert result.error.retryable is True


def test_failure_is_isolated_to_its_own_request() -> None:
    failing = memory.InMemoryMcpClient(
        responses={},
        errors={"get_error_logs": ConnectionError("mcp down")},
    )
    healthy = memory.InMemoryMcpClient(
        responses={"get_video_status": memory.ToolReply(data={"state": "OK"})}
    )
    request = models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="bad",
                source=models.Source.LOGGING,
                query_type="error_logs",
                params={},
            ),
            models.EvidenceRequest(
                request_id="good",
                source=models.Source.SPANNER,
                query_type="video_status",
                params={},
            ),
        ),
    )

    by_id = {
        r.request_id: r
        for r in _collect(
            request,
            {
                models.Source.LOGGING: failing,
                models.Source.SPANNER: healthy,
            },
        ).results
    }

    assert by_id["bad"].error is not None
    assert by_id["bad"].error.retryable is True
    assert by_id["bad"].data is None
    assert by_id["good"].error is None
    assert by_id["good"].data == {"state": "OK"}


def test_transport_failure_is_retryable_but_permanent_is_not() -> None:
    request = models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="timeout",
                source=models.Source.LOGGING,
                query_type="error_logs",
                params={},
            ),
            models.EvidenceRequest(
                request_id="permanent",
                source=models.Source.SPANNER,
                query_type="video_status",
                params={},
            ),
        ),
    )
    timeout_client = memory.InMemoryMcpClient(
        responses={}, errors={"get_error_logs": TimeoutError("slow")}
    )
    permanent_client = memory.InMemoryMcpClient(
        responses={}, errors={"get_video_status": ValueError("bad arg")}
    )

    by_id = {
        r.request_id: r
        for r in _collect(
            request,
            {
                models.Source.LOGGING: timeout_client,
                models.Source.SPANNER: permanent_client,
            },
        ).results
    }

    assert by_id["timeout"].error.retryable is True
    assert by_id["permanent"].error.retryable is False


def test_over_limit_request_is_clamped_before_dispatch() -> None:
    logging_client = memory.InMemoryMcpClient(
        responses={"get_error_logs": memory.ToolReply(data=[])}
    )
    request = models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="req-1",
                source=models.Source.LOGGING,
                query_type="error_logs",
                params={"limit": 100_000, "service": "worker"},
            ),
        ),
    )

    result = _collect(request, {models.Source.LOGGING: logging_client}).results[
        0
    ]

    # The MCP never sees the unsafe original value.
    _tool, sent_params = logging_client.calls[0]
    assert sent_params["limit"] == 500
    # Provenance reflects the value actually used.
    assert result.params_used["limit"] == 500
    assert result.params_used["service"] == "worker"


def test_live_source_without_a_healthy_client_is_unavailable() -> None:
    # A live source (logging) whose MCP subprocess is unhealthy is represented
    # by the absence of a client for it. The request must degrade cleanly.
    request = models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="req-1",
                source=models.Source.LOGGING,
                query_type="error_logs",
                params={},
            ),
        ),
    )

    result = _collect(request, {}).results[0]

    assert result.error is not None
    assert result.error.code == "source_unavailable"
    assert result.error.retryable is True
    assert result.data is None
