"""Uvicorn entrypoint for the Data Collector Cloud Run service."""

import os


def main() -> None:
    """Serves the collect_data A2A app on the configured port."""
    import uvicorn

    uvicorn.run(
        "data_collector.__main__:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
    )
