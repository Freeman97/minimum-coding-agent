"""Shared pytest fixtures for the minimum-coding-agent test suite."""

from __future__ import annotations

import pytest

#: Environment variables that configure the application.
MCA_ENV_VARS: tuple[str, ...] = (
    "MCA_BASE_URL",
    "MCA_API_KEY",
    "MCA_MODEL",
    "MCA_CONFIG",
    "MCA_WORKSPACE",
)


@pytest.fixture(autouse=True)
def _clean_mca_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove MCA_* variables so tests do not depend on the developer shell."""
    for name in MCA_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
