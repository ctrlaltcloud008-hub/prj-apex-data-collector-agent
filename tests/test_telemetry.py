"""Behavior tests for per-tool-call telemetry emission."""

import asyncio

from data_collector import collector, memory, models


def _collect(request, clients, sink):
    """Drives the collector with an injected telemetry sink."""
    return asyncio.run(collector.collect(request, clients, sink=sink))


def _one(source, query_type):
    """Builds a single-request batch for terseness."""
    return models.CollectRequest(
        investigation_id="investigation-1",
        requests=(
            models.EvidenceRequest(
                request_id="req-1",
                source=source,
                query_type=query_type,
                params={},
            ),
        ),
    )


def test_successful_call_emits_one_record_with_provenance() -> None:
    sink = memory.InMemoryTelemetrySink()
    logging_client = memory.InMemoryMcpClient(
        responses={"get_error_logs": memory.ToolReply(data=[1, 2, 3])}
    )

    _collect(
        _one(models.Source.LOGGING, "error_logs"),
        {models.Source.LOGGING: logging_client},
        sink,
    )

    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.investigation_id == "investigation-1"
    assert record.request_id == "req-1"
    assert record.source is models.Source.LOGGING
    assert record.tool_called == "get_error_logs"
    assert record.record_count == 3
    assert record.duration_ms >= 0
    assert record.outcome == "success"


def test_errored_call_emits_record_tagged_with_error_code() -> None:
    sink = memory.InMemoryTelemetrySink()
    failing = memory.InMemoryMcpClient(
        responses={}, errors={"get_error_logs": ConnectionError("down")}
    )

    _collect(
        _one(models.Source.LOGGING, "error_logs"),
        {models.Source.LOGGING: failing},
        sink,
    )

    assert sink.records[0].outcome == "transport_error"


def test_validation_reject_and_unavailable_each_emit_a_record() -> None:
    sink = memory.InMemoryTelemetrySink()
    logging_client = memory.InMemoryMcpClient(responses={})

    # Validation reject: a live, present source with an unknown query_type.
    _collect(
        _one(models.Source.LOGGING, "nope"),
        {models.Source.LOGGING: logging_client},
        sink,
    )
    # Unavailable: a source whose MCP is not wired.
    _collect(_one(models.Source.GKE, "pods"), {}, sink)

    assert [r.outcome for r in sink.records] == [
        "validation_error",
        "source_unavailable",
    ]
