"""Versioned service-to-runtime resource mappings.

Which Cloud Run deployment, Pub/Sub subscription, or GKE workload backs a given
pipeline service is deployment inventory, not something a model may infer. The
mapping is loaded from a versioned configuration file generated from the
knowledge graph or deployment inventory and treated as read-only reference data.
"""

import dataclasses
import json
import pathlib
import typing


@dataclasses.dataclass(frozen=True)
class ResourceMap:
    """A versioned snapshot of service-to-runtime resource mappings."""

    version: str
    mappings: typing.Mapping[str, typing.Mapping[str, str]]

    def runtime_for(self, service: str) -> typing.Mapping[str, str] | None:
        """Returns the runtime resources for a service, or ``None``."""
        return self.mappings.get(service)


def load_resource_map(path: str | pathlib.Path) -> ResourceMap:
    """Loads a versioned resource map from a JSON file.

    Raises ``FileNotFoundError`` if the versioned configuration is absent; the
    collector must not fall back to inferred mappings.
    """
    document = json.loads(pathlib.Path(path).read_text())
    return ResourceMap(
        version=document["version"],
        mappings=document.get("mappings", {}),
    )
