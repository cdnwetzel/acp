"""Tests read the shipped endpoints.example.json, never an operator's local
endpoints.json: the suite must pass on a fresh clone and must not depend on, or
reveal, a real deployment's hosts."""
import pytest

from pipeline import endpoints


@pytest.fixture(autouse=True)
def _example_endpoint_manifest(monkeypatch):
    monkeypatch.setattr(endpoints, "MANIFEST", endpoints.EXAMPLE)
