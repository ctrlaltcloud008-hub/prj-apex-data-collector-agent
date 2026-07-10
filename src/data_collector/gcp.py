"""Real read-only MCP adapters backed by FastMCP over streamable HTTP.

Each operational MCP (logging, spanner, pubsub, and later metrics, trace, gke)
is a FastMCP ``streamable-http`` server. ``FastMcpClient`` is a thin, read-only
transport that calls one allowlisted tool and returns its raw result with a
record count. It performs no routing and no interpretation.
"""

import typing

import fastmcp

from data_collector import models, ports


def _record_count(data: typing.Any) -> int:
    """Derives a record count from a raw MCP payload."""
    if data is None:
        return 0
    if isinstance(data, list):
        return len(data)
    return 1


class FastMcpClient:
    """Calls one MCP's tools over FastMCP transport.

    ``target`` is whatever ``fastmcp.Client`` accepts: a streamable-HTTP URL in
    production, or an in-memory ``FastMCP`` server in tests.
    """

    def __init__(self, target: typing.Any) -> None:
        self._target = target

    async def call_tool(
        self, tool: str, params: typing.Mapping[str, typing.Any]
    ) -> ports.ToolResult:
        """Invokes one tool and returns its raw result and record count."""
        async with fastmcp.Client(self._target) as client:
            result = await client.call_tool(tool, dict(params))
        data = result.data
        return ports.ToolResult(data=data, record_count=_record_count(data))


class OtelPubSubTelemetrySink:
    """Emits one OpenTelemetry span and one Pub/Sub event per tool call."""

    def __init__(self, project_id: str, topic_id: str) -> None:
        from google.cloud import pubsub_v1

        self._publisher = pubsub_v1.PublisherClient()
        self._topic = self._publisher.topic_path(project_id, topic_id)

    async def emit(self, record: models.ToolCallTelemetry) -> None:
        """Spans and publishes one evidence request's observability."""
        import json

        from opentelemetry import trace

        tracer = trace.get_tracer("data_collector")
        attributes = {
            "investigation_id": record.investigation_id,
            "request_id": record.request_id,
            "source": record.source.value,
            "tool_called": record.tool_called or "",
            "record_count": record.record_count,
            "duration_ms": record.duration_ms,
            "outcome": record.outcome,
        }
        with tracer.start_as_current_span("mcp.call_tool") as span:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        self._publisher.publish(self._topic, json.dumps(attributes).encode())
