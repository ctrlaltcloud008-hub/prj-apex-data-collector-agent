"""Unit tests for server-side evidence request limits."""

from data_collector import limits, models


def test_logging_limit_defaults_to_100_when_absent() -> None:
    applied = limits.enforce(models.Source.LOGGING, {})

    assert applied["limit"] == limits.DEFAULT_LOGGING_LIMIT == 100


def test_logging_limit_is_clamped_to_hard_max() -> None:
    applied = limits.enforce(models.Source.LOGGING, {"limit": 100_000})

    assert applied["limit"] == limits.MAX_LOGGING_LIMIT == 500


def test_lookback_rows_and_timeout_are_clamped() -> None:
    applied = limits.enforce(
        models.Source.SPANNER,
        {
            "lookback_seconds": 10**9,
            "rows": 10_000,
            "timeout_ms": 10**9,
        },
    )

    assert applied["lookback_seconds"] == limits.MAX_LOOKBACK_SECONDS
    assert applied["rows"] == limits.MAX_ROWS
    assert applied["timeout_ms"] == limits.MAX_TIMEOUT_MS


def test_within_limit_values_pass_through_unchanged() -> None:
    applied = limits.enforce(
        models.Source.LOGGING, {"limit": 25, "service": "worker"}
    )

    assert applied["limit"] == 25
    assert applied["service"] == "worker"
