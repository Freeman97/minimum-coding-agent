"""Shared pytest fixtures for the minimum-coding-agent test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

#: Directory with reusable test doubles shared across test modules.
FIXTURES_DIR = Path(__file__).parent / "fixtures"
if str(FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURES_DIR))

#: Environment variables that configure the application.
MCA_ENV_VARS: tuple[str, ...] = (
    "MCA_BASE_URL",
    "MCA_API_KEY",
    "MCA_MODEL",
    "MCA_CONFIG",
    "MCA_WORKSPACE",
)

#: Bare names that must never influence the configuration (only MCA_* is read).
BARE_ENV_NAMES: tuple[str, ...] = (
    "BASE_URL",
    "API_KEY",
    "MODEL",
    "CONFIG",
    "WORKSPACE",
)


@pytest.fixture(autouse=True)
def _clean_mca_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ambient configuration variables so the suite is hermetic."""
    for name in (*MCA_ENV_VARS, *BARE_ENV_NAMES):
        monkeypatch.delenv(name, raising=False)
