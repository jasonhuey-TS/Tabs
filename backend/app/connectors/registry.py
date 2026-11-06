"""Connector registry. Connectors register themselves with @register."""
from __future__ import annotations

_REGISTRY: dict = {}


def register(cls):
    """Class decorator: instantiate the connector and add it to the library."""
    instance = cls()
    if not instance.key:
        raise ValueError(f"{cls.__name__} must define a key")
    _REGISTRY[instance.key] = instance
    return cls


def get(key: str):
    return _REGISTRY.get(key)


def all_connectors() -> list:
    return list(_REGISTRY.values())
