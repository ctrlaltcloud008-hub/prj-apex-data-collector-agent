"""Static, deterministic mapping from evidence requests to MCP tools.

Tool selection comes only from this table, never from model inference. An
unknown ``(source, query_type)`` combination has no entry and is rejected by
the collector as a per-request validation error without invoking any MCP.

All six sources are wired: logging, spanner, pubsub, metrics, trace, and gke.
A source still degrades to ``source_unavailable`` at runtime when its MCP
client is not configured or unhealthy.
"""

import typing

from data_collector import models

Params = typing.Mapping[str, typing.Any]

# Sources whose MCPs are deployed and wired.
LIVE_SOURCES: frozenset[models.Source] = frozenset(
    {
        models.Source.LOGGING,
        models.Source.SPANNER,
        models.Source.PUBSUB,
        models.Source.METRICS,
        models.Source.TRACE,
        models.Source.GKE,
    }
)


def is_available(source: models.Source) -> bool:
    """Returns whether ``source``'s MCP is deployed and wired today."""
    return source in LIVE_SOURCES


# Static one-to-one routes: one tool per (source, query_type).
_ROUTES: dict[tuple[models.Source, str], str] = {
    (models.Source.LOGGING, "error_logs"): "get_error_logs",
    (models.Source.LOGGING, "audit_logs"): "get_audit_logs",
    (models.Source.LOGGING, "structured_search"): "search_structured_logs",
    (models.Source.LOGGING, "logs_around_time"): "get_logs_around_time",
    (models.Source.SPANNER, "video_status"): "get_video_status",
    (models.Source.SPANNER, "stuck_videos"): "get_stuck_videos",
    (models.Source.SPANNER, "lifecycle"): "get_lifecycle_events",
    (models.Source.SPANNER, "outbox"): "get_outbox_pending_count",
    (models.Source.SPANNER, "recent_failures"): "get_recent_failures",
    (models.Source.PUBSUB, "subscription_stats"): "get_subscription_stats",
    (models.Source.PUBSUB, "oldest_unacked_age"): "get_oldest_unacked_age",
    (models.Source.PUBSUB, "dlq_sample"): "get_dlq_messages",
    (
        models.Source.PUBSUB,
        "topic_subscriptions",
    ): "list_subscriptions_for_topic",
    # metrics-mcp (design 08) tool names.
    (models.Source.METRICS, "error_rate"): "get_error_rate",
    (models.Source.METRICS, "backlog"): "get_pubsub_backlog",
    (models.Source.METRICS, "latency"): "get_processing_latency",
    # trace-mcp (design 09) tool names.
    (models.Source.TRACE, "trace_by_video"): "get_trace_by_video_id",
    (models.Source.TRACE, "failed_traces"): "find_failed_traces",
    (models.Source.TRACE, "trace_by_id"): "get_trace",
    # gke-mcp (design 12) tool names.
    (models.Source.GKE, "pods"): "get_pod_status",
    (models.Source.GKE, "pod_logs"): "get_pod_logs_tail",
}


def _spanner_stages(params: Params) -> str:
    """Chooses a stages tool: per-video records vs. the stage catalog."""
    if "video_id" in params:
        return "get_stage_records"
    return "get_pipeline_stages"


def _spanner_jobs(params: Params) -> str:
    """Chooses a jobs tool: only-stalled vs. all transcode jobs."""
    if params.get("stalled"):
        return "get_stalled_transcode_jobs"
    return "get_transcode_jobs"


# Dynamic routes: the tool depends on the request's params shape.
_DYNAMIC_ROUTES: dict[
    tuple[models.Source, str], typing.Callable[[Params], str]
] = {
    (models.Source.SPANNER, "stages"): _spanner_stages,
    (models.Source.SPANNER, "jobs"): _spanner_jobs,
}


def route(
    source: models.Source,
    query_type: str,
    params: Params | None = None,
) -> str | None:
    """Returns the MCP tool for a request, or ``None`` if unrouted."""
    dynamic = _DYNAMIC_ROUTES.get((source, query_type))
    if dynamic is not None:
        return dynamic(params or {})
    return _ROUTES.get((source, query_type))
