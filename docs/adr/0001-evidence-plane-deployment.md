# ADR 0001: Evidence-plane deployment, identity, and health model

Status: Proposed — pending human review

## Context

The Data Collector is the deterministic evidence router between the Diagnosis
Agent and the read-only operational MCPs. It must never mutate operational state
and must degrade cleanly when a source is unavailable. Three decisions in this
area are architectural and are flagged here for explicit human review rather
than being settled silently in code.

## Decision

### 1. Least-privilege read-only identity

The service runs as a private Cloud Run service under a dedicated service
account holding only read roles. Proposed role set (**needs human review**):

- `roles/logging.viewer` — logging MCP
- `roles/spanner.databaseReader` — spanner MCP (operational database, read-only)
- `roles/pubsub.viewer` and `roles/monitoring.viewer` — pubsub MCP subscription
  and backlog observations without consuming messages
- `roles/pubsub.publisher` — scoped only to the analytics events topic

No write, admin, or actuation roles are granted. Only the Remediator holds
operational write permissions elsewhere in the system.

### 2. MCP sidecar topology and independent health

The read-only MCPs (logging, spanner, pubsub) are deployed as sidecar
containers in the same Cloud Run service and reached over localhost, each with
its own liveness/readiness check. The collector composes the client map from
sources whose sidecar is healthy; an unhealthy or not-yet-started sidecar is
represented by the absence of its client, and every request to that source
returns `source_unavailable` (retryable) instead of failing the service. The
metrics, trace, and gke sources are not wired yet and always resolve to
`source_unavailable`.

### 3. Versioned resource mappings, never inferred

Service-to-runtime resource mappings (which deployment / subscription / workload
backs a pipeline service) load from a versioned JSON configuration generated
from the knowledge graph or deployment inventory (`config.load_resource_map`).
The collector must not infer these mappings; a missing configuration is an error.

## Consequences

- The identity role set above must be reviewed and approved before deployment.
- Ingress is private (internal only); the Diagnosis Agent calls the collector
  over authenticated A2A with caller identity required.
- Broadening the evidence plane (metrics/trace/gke) is additive: deploy the
  sidecar, add its `*_MCP_URL`, and register the source as live.
