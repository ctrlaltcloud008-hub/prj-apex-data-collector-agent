"""Unit tests for the static evidence routing table."""

import pytest

from data_collector import models, routing

_LIVE_ROUTES = [
    (models.Source.LOGGING, "error_logs", {}, "get_error_logs"),
    (models.Source.LOGGING, "audit_logs", {}, "get_audit_logs"),
    (models.Source.LOGGING, "structured_search", {}, "search_structured_logs"),
    (models.Source.LOGGING, "logs_around_time", {}, "get_logs_around_time"),
    (models.Source.SPANNER, "video_status", {}, "get_video_status"),
    (models.Source.SPANNER, "stuck_videos", {}, "get_stuck_videos"),
    (models.Source.SPANNER, "lifecycle", {}, "get_lifecycle_events"),
    (models.Source.SPANNER, "outbox", {}, "get_outbox_pending_count"),
    (models.Source.SPANNER, "recent_failures", {}, "get_recent_failures"),
    (models.Source.PUBSUB, "subscription_stats", {}, "get_subscription_stats"),
    (models.Source.PUBSUB, "oldest_unacked_age", {}, "get_oldest_unacked_age"),
    (models.Source.PUBSUB, "dlq_sample", {}, "get_dlq_messages"),
    (
        models.Source.PUBSUB,
        "topic_subscriptions",
        {},
        "list_subscriptions_for_topic",
    ),
]


@pytest.mark.parametrize("source, query_type, params, tool", _LIVE_ROUTES)
def test_live_routes_map_to_expected_tool(
    source: models.Source,
    query_type: str,
    params: dict,
    tool: str,
) -> None:
    assert routing.route(source, query_type, params) == tool


def test_spanner_stages_selects_tool_from_params_shape() -> None:
    assert (
        routing.route(models.Source.SPANNER, "stages", {"video_id": "v1"})
        == "get_stage_records"
    )
    assert (
        routing.route(models.Source.SPANNER, "stages", {})
        == "get_pipeline_stages"
    )


def test_spanner_jobs_selects_tool_from_params_shape() -> None:
    assert (
        routing.route(models.Source.SPANNER, "jobs", {"stalled": True})
        == "get_stalled_transcode_jobs"
    )
    assert (
        routing.route(models.Source.SPANNER, "jobs", {}) == "get_transcode_jobs"
    )


def test_unknown_combination_is_unrouted() -> None:
    assert routing.route(models.Source.LOGGING, "not_a_query", {}) is None
    assert routing.route(models.Source.SPANNER, "error_logs", {}) is None


def test_metrics_trace_gke_sources_are_live() -> None:
    """The metrics/trace/gke MCPs have landed; their sources route."""
    for source in (
        models.Source.METRICS,
        models.Source.TRACE,
        models.Source.GKE,
    ):
        assert routing.is_available(source)


def test_metrics_routes_match_metrics_mcp_tool_names() -> None:
    assert routing.route(models.Source.METRICS, "error_rate") == (
        "get_error_rate"
    )
    assert routing.route(models.Source.METRICS, "backlog") == (
        "get_pubsub_backlog"
    )
    assert routing.route(models.Source.METRICS, "latency") == (
        "get_processing_latency"
    )


def test_trace_routes_match_trace_mcp_tool_names() -> None:
    assert routing.route(models.Source.TRACE, "trace_by_video") == (
        "get_trace_by_video_id"
    )
    assert routing.route(models.Source.TRACE, "failed_traces") == (
        "find_failed_traces"
    )
    assert routing.route(models.Source.TRACE, "trace_by_id") == "get_trace"


def test_gke_routes_match_gke_mcp_tool_names() -> None:
    assert routing.route(models.Source.GKE, "pods") == "get_pod_status"
    assert routing.route(models.Source.GKE, "pod_logs") == (
        "get_pod_logs_tail"
    )
