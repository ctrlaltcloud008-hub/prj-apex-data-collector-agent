"""A2A HTTP shell for the deterministic evidence collector."""

import os
import typing

import fastapi
import pydantic

from data_collector import collector, gcp, models, ports

# Sources whose MCPs are deployed today, mapped to the env var holding the
# MCP's streamable-HTTP URL. Sources absent here resolve to source_unavailable.
_LIVE_SOURCE_URLS: dict[models.Source, str] = {
    models.Source.LOGGING: "LOGGING_MCP_URL",
    models.Source.SPANNER: "SPANNER_MCP_URL",
    models.Source.PUBSUB: "PUBSUB_MCP_URL",
    models.Source.METRICS: "METRICS_MCP_URL",
    models.Source.TRACE: "TRACE_MCP_URL",
    models.Source.GKE: "GKE_MCP_URL",
}


class EvidenceRequestBody(pydantic.BaseModel):
    """One typed evidence request in a collect_data call."""

    request_id: str
    source: models.Source
    query_type: str
    params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    priority: models.Priority = models.Priority.BLOCKING
    intent: str | None = None


class CollectDataTask(pydantic.BaseModel):
    """The collect_data A2A task submitted by the Diagnosis Agent."""

    task_type: typing.Literal["collect_data"]
    investigation_id: str
    requests: list[EvidenceRequestBody]


def _is_local() -> bool:
    """Returns whether hermetic adapters should be used."""
    return os.environ.get("ENV", "local") == "local"


def _required_environment(name: str) -> str:
    """Returns a required production configuration value."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_mcp_clients() -> typing.Mapping[models.Source, ports.McpClient]:
    """Returns the configured read-only MCP client per live source."""
    if _is_local():
        return {}
    return {
        source: gcp.FastMcpClient(_required_environment(env_var))
        for source, env_var in _LIVE_SOURCE_URLS.items()
    }


class _NullTelemetrySink:
    """A telemetry sink that drops records, used for local runs."""

    async def emit(self, record: models.ToolCallTelemetry) -> None:
        """Ignores the record."""


def get_telemetry_sink() -> ports.TelemetrySink:
    """Returns the configured telemetry sink."""
    if _is_local():
        return _NullTelemetrySink()
    return gcp.OtelPubSubTelemetrySink(
        project_id=_required_environment("GCP_PROJECT_ID"),
        topic_id=_required_environment("ANALYTICS_TOPIC_ID"),
    )


app = fastapi.FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe for the collector service itself.

    Per-MCP-subprocess health is reflected per request: an unhealthy source is
    reported as ``source_unavailable`` rather than failing this probe.
    """
    return {"status": "ok"}


@app.post("/v1/collect_data")
async def collect_data(
    task: CollectDataTask,
    clients: typing.Annotated[
        typing.Mapping[models.Source, ports.McpClient],
        fastapi.Depends(get_mcp_clients),
    ],
    sink: typing.Annotated[
        ports.TelemetrySink, fastapi.Depends(get_telemetry_sink)
    ],
) -> dict[str, typing.Any]:
    """Routes a batch of evidence requests to the read-only MCPs."""
    request = models.CollectRequest(
        investigation_id=task.investigation_id,
        requests=tuple(
            models.EvidenceRequest(
                request_id=item.request_id,
                source=item.source,
                query_type=item.query_type,
                params=item.params,
                priority=item.priority,
                intent=item.intent,
            )
            for item in task.requests
        ),
    )
    response = await collector.collect(request, clients, sink=sink)
    return _serialize(response)


def _serialize(response: models.CollectResponse) -> dict[str, typing.Any]:
    """Renders a collect response as the documented JSON contract."""
    return {
        "investigation_id": response.investigation_id,
        "results": [
            {
                "request_id": result.request_id,
                "source": result.source.value,
                "tool_called": result.tool_called,
                "params_used": dict(result.params_used),
                "record_count": result.record_count,
                "data": result.data,
                "collected_at": result.collected_at.isoformat(),
                "duration_ms": result.duration_ms,
                "error": (
                    None
                    if result.error is None
                    else {
                        "code": result.error.code,
                        "message": result.error.message,
                        "retryable": result.error.retryable,
                    }
                ),
            }
            for result in response.results
        ],
    }
