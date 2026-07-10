"""Behavior tests for the versioned resource-mapping loader."""

import json
import pathlib

import pytest

from data_collector import config


def test_loads_versioned_service_to_runtime_mappings(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "resource_map.json"
    path.write_text(
        json.dumps(
            {
                "version": "2026-07-04T00:00:00Z",
                "mappings": {
                    "transcode-worker": {
                        "deployment": "transcode-worker",
                        "subscription": "transcode-jobs-sub",
                    }
                },
            }
        )
    )

    resource_map = config.load_resource_map(path)

    assert resource_map.version == "2026-07-04T00:00:00Z"
    assert resource_map.runtime_for("transcode-worker") == {
        "deployment": "transcode-worker",
        "subscription": "transcode-jobs-sub",
    }


def test_unknown_service_has_no_mapping(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "resource_map.json"
    path.write_text(json.dumps({"version": "v1", "mappings": {}}))

    resource_map = config.load_resource_map(path)

    assert resource_map.runtime_for("nope") is None


def test_missing_config_file_is_an_error(tmp_path: pathlib.Path) -> None:
    with pytest.raises(FileNotFoundError):
        config.load_resource_map(tmp_path / "absent.json")
