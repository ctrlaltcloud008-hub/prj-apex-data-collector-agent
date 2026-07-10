"""Public domain types for deterministic evidence collection."""

import dataclasses
import datetime
import enum
import typing


class Source(enum.StrEnum):
    """A read-only operational plane the collector can route to."""

    LOGGING = "logging"
    METRICS = "metrics"
    TRACE = "trace"
    SPANNER = "spanner"
    PUBSUB = "pubsub"
    GKE = "gke"


class Priority(enum.StrEnum):
    """Scheduling class for one evidence request."""

    BLOCKING = "blocking"
    BACKGROUND = "background"


@dataclasses.dataclass(frozen=True)
class EvidenceRequest:
    """One typed evidence read the Diagnosis Agent asks the collector for.

    ``intent`` is carried for audit and human readability only; it never
    influences which MCP tool the request routes to.
    """

    request_id: str
    source: Source
    query_type: str
    params: typing.Mapping[str, typing.Any] = dataclasses.field(
        default_factory=dict
    )
    priority: Priority = Priority.BLOCKING
    intent: str | None = None


@dataclasses.dataclass(frozen=True)
class CollectRequest:
    """A batch of evidence requests scoped to one Investigation."""

    investigation_id: str
    requests: tuple[EvidenceRequest, ...]


@dataclasses.dataclass(frozen=True)
class EvidenceError:
    """A typed, per-request failure that never fails the whole batch."""

    code: str
    message: str
    retryable: bool


@dataclasses.dataclass(frozen=True)
class EvidenceResult:
    """The provenance-tagged outcome of one evidence request."""

    request_id: str
    source: Source
    tool_called: str | None
    params_used: typing.Mapping[str, typing.Any]
    record_count: int
    data: typing.Any
    collected_at: datetime.datetime
    duration_ms: int
    error: EvidenceError | None = None


@dataclasses.dataclass(frozen=True)
class CollectResponse:
    """The collector's response for one Investigation's evidence batch."""

    investigation_id: str
    results: tuple[EvidenceResult, ...]


@dataclasses.dataclass(frozen=True)
class ToolCallTelemetry:
    """One observability record for a single evidence request.

    ``outcome`` is ``"success"`` for a completed tool call, or the evidence
    error code (``source_unavailable``, ``validation_error``, ``timeout``,
    ``transport_error``, ``mcp_error``) otherwise.
    """

    investigation_id: str
    request_id: str
    source: Source
    tool_called: str | None
    record_count: int
    duration_ms: int
    outcome: str
