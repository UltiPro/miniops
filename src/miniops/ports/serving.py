from typing import Protocol


class ServingBackend(Protocol):
    """Starts, stops and lists deployments on a target."""


class ImageRegistry(Protocol):
    """Stores container images for a target."""
