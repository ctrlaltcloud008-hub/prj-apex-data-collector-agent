"""Boundary protocols used by the evidence collector."""

import dataclasses
import typing

from data_collector import models


@dataclasses.dataclass(frozen=True)
class ToolResult:
    """The raw result of one MCP tool call.

    ``record_count`` is the count reported by the MCP; the collector does not
    reinterpret the payload.
    """

    data: typing.Any
    record_count: int


class McpClient(typing.Protocol):
    """A read-only client for one operational MCP source."""

    async def call_tool(
        self, tool: str, params: typing.Mapping[str, typing.Any]
    ) -> ToolResult:
        """Invokes one allowlisted tool and returns its raw result."""
        ...


class TelemetrySink(typing.Protocol):
    """Emits one span and one analytics event per evidence request."""

    async def emit(self, record: models.ToolCallTelemetry) -> None:
        """Records observability for one completed evidence request."""
        ...
