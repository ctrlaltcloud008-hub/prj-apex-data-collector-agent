"""Behavior tests for the collect_data A2A HTTP endpoint."""

from fastapi import testclient

from data_collector import __main__ as main_module
from data_collector import memory, models


def _client_with_sources(
    clients: dict[models.Source, memory.InMemoryMcpClient],
) -> testclient.TestClient:
    """Returns a TestClient whose MCP clients are the given fakes."""
    main_module.app.dependency_overrides[main_module.get_mcp_clients] = (
        lambda: clients
    )
    return testclient.TestClient(main_module.app)


def test_collect_data_endpoint_returns_routed_result() -> None:
    logging_client = memory.InMemoryMcpClient(
        responses={"get_error_logs": memory.ToolReply(data=[{"msg": "boom"}])}
    )
    client = _client_with_sources({models.Source.LOGGING: logging_client})

    response = client.post(
        "/v1/collect_data",
        json={
            "task_type": "collect_data",
            "investigation_id": "investigation-1",
            "requests": [
                {
                    "request_id": "req-1",
                    "source": "logging",
                    "query_type": "error_logs",
                    "params": {"service": "transcode-worker"},
                    "priority": "blocking",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["investigation_id"] == "investigation-1"
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["request_id"] == "req-1"
    assert result["tool_called"] == "get_error_logs"
    assert result["data"] == [{"msg": "boom"}]
    assert result["error"] is None

    main_module.app.dependency_overrides.clear()


def test_batch_returns_200_even_when_a_request_errors() -> None:
    client = _client_with_sources({})

    response = client.post(
        "/v1/collect_data",
        json={
            "task_type": "collect_data",
            "investigation_id": "investigation-1",
            "requests": [
                {
                    "request_id": "unavailable",
                    "source": "gke",
                    "query_type": "pods",
                    "params": {},
                }
            ],
        },
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["error"]["code"] == "source_unavailable"
    assert result["error"]["retryable"] is True

    main_module.app.dependency_overrides.clear()
