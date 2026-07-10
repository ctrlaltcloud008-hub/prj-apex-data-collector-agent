"""Behavior tests for the real FastMCP-backed evidence adapter."""

import asyncio

from fastmcp import FastMCP

from data_collector import gcp, ports


def _in_memory_logging_server() -> FastMCP:
    """A minimal FastMCP server standing in for the logging MCP."""
    server: FastMCP = FastMCP("logging-mcp-fake")

    @server.tool
    def get_error_logs(service: str) -> list[dict]:
        """Returns canned error logs for a service."""
        return [{"service": service, "msg": "boom"}]

    return server


def test_fastmcp_client_calls_tool_and_returns_provenance() -> None:
    adapter = gcp.FastMcpClient(_in_memory_logging_server())

    result = asyncio.run(
        adapter.call_tool("get_error_logs", {"service": "transcode-worker"})
    )

    assert isinstance(result, ports.ToolResult)
    assert result.data == [{"service": "transcode-worker", "msg": "boom"}]
    assert result.record_count == 1
