"""Hermetic in-memory adapters for tests and local runs."""

import asyncio
import dataclasses
import typing

from data_collector import models, ports


@dataclasses.dataclass
class ToolReply:
    """A canned reply for one tool, with an optional record count."""

    data: typing.Any
    record_count: int | None = None


class InMemoryMcpClient:
    """An MCP client that replays canned replies keyed by tool name."""

    def __init__(
        self,
        responses: dict[str, ToolReply],
        errors: dict[str, Exception] | None = None,
        delay: float = 0.0,
    ) -> None:
        self._responses = responses
        self._errors = errors or {}
        self._delay = delay
        self.calls: list[tuple[str, typing.Mapping[str, typing.Any]]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def call_tool(
        self, tool: str, params: typing.Mapping[str, typing.Any]
    ) -> ports.ToolResult:
        """Records the call and returns the canned reply for ``tool``."""
        self.calls.append((tool, params))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self._delay:
                await asyncio.sleep(self._delay)
            if tool in self._errors:
                raise self._errors[tool]
            reply = self._responses[tool]
        finally:
            self.in_flight -= 1
        record_count = reply.record_count
        if record_count is None:
            record_count = (
                len(reply.data) if isinstance(reply.data, list) else 1
            )
        return ports.ToolResult(data=reply.data, record_count=record_count)


class InMemoryTelemetrySink:
    """A telemetry sink that captures emitted records for assertions."""

    def __init__(self) -> None:
        self.records: list[models.ToolCallTelemetry] = []

    async def emit(self, record: models.ToolCallTelemetry) -> None:
        """Appends one telemetry record."""
        self.records.append(record)
