"""Behavior tests for blocking-first streaming and bounded concurrency."""

import asyncio

from data_collector import collector, memory, models


def _request(*evidence: models.EvidenceRequest) -> models.CollectRequest:
    return models.CollectRequest(
        investigation_id="investigation-1", requests=evidence
    )


def _evidence(
    request_id, source, query_type, priority
) -> models.EvidenceRequest:
    return models.EvidenceRequest(
        request_id=request_id,
        source=source,
        query_type=query_type,
        params={},
        priority=priority,
    )


def test_blocking_results_stream_before_background() -> None:
    fast_blocking = memory.InMemoryMcpClient(
        responses={"get_error_logs": memory.ToolReply(data=[])}
    )
    slow_background = memory.InMemoryMcpClient(
        responses={"get_video_status": memory.ToolReply(data={})}, delay=0.05
    )
    request = _request(
        _evidence(
            "bg",
            models.Source.SPANNER,
            "video_status",
            models.Priority.BACKGROUND,
        ),
        _evidence(
            "block",
            models.Source.LOGGING,
            "error_logs",
            models.Priority.BLOCKING,
        ),
    )

    async def run() -> list[str]:
        seen = []
        async for result in collector.collect_stream(
            request,
            {
                models.Source.LOGGING: fast_blocking,
                models.Source.SPANNER: slow_background,
            },
        ):
            seen.append(result.request_id)
        return seen

    order = asyncio.run(run())

    assert order[0] == "block"
    assert order[-1] == "bg"


def test_background_concurrency_respects_limit() -> None:
    source = memory.InMemoryMcpClient(
        responses={"get_video_status": memory.ToolReply(data={})}, delay=0.02
    )
    request = _request(
        *[
            _evidence(
                f"bg-{i}",
                models.Source.SPANNER,
                "video_status",
                models.Priority.BACKGROUND,
            )
            for i in range(6)
        ]
    )

    asyncio.run(
        collector.collect(
            request,
            {models.Source.SPANNER: source},
            background_concurrency=2,
        )
    )

    assert source.max_in_flight <= 2


def test_failing_request_does_not_stall_the_batch() -> None:
    failing = memory.InMemoryMcpClient(
        responses={}, errors={"get_error_logs": ConnectionError("down")}
    )
    healthy = memory.InMemoryMcpClient(
        responses={"get_video_status": memory.ToolReply(data={"ok": True})}
    )
    request = _request(
        _evidence(
            "bad",
            models.Source.LOGGING,
            "error_logs",
            models.Priority.BLOCKING,
        ),
        _evidence(
            "good",
            models.Source.SPANNER,
            "video_status",
            models.Priority.BLOCKING,
        ),
    )

    response = asyncio.run(
        collector.collect(
            request,
            {
                models.Source.LOGGING: failing,
                models.Source.SPANNER: healthy,
            },
        )
    )

    by_id = {r.request_id: r for r in response.results}
    assert by_id["bad"].error is not None
    assert by_id["good"].data == {"ok": True}


def test_batch_response_preserves_request_order() -> None:
    logging_client = memory.InMemoryMcpClient(
        responses={"get_error_logs": memory.ToolReply(data=[])}, delay=0.03
    )
    spanner_client = memory.InMemoryMcpClient(
        responses={"get_video_status": memory.ToolReply(data={})}
    )
    request = _request(
        _evidence(
            "first",
            models.Source.LOGGING,
            "error_logs",
            models.Priority.BLOCKING,
        ),
        _evidence(
            "second",
            models.Source.SPANNER,
            "video_status",
            models.Priority.BLOCKING,
        ),
    )

    response = asyncio.run(
        collector.collect(
            request,
            {
                models.Source.LOGGING: logging_client,
                models.Source.SPANNER: spanner_client,
            },
        )
    )

    assert [r.request_id for r in response.results] == ["first", "second"]
