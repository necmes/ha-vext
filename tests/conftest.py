"""Shared fixtures for the Vext integration tests."""
from __future__ import annotations

import pathlib

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

# pytest-homeassistant-custom-component ships its own `custom_components`
# package, which shadows the one in this repository. Add ours to that package's
# search path so Home Assistant's loader discovers `vext`.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _register_repo_custom_components() -> None:
    import custom_components  # noqa: PLC0415

    ours = str(_REPO_ROOT / "custom_components")
    if ours not in custom_components.__path__:
        custom_components.__path__.insert(0, ours)


_register_repo_custom_components()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load `custom_components/vext` during tests."""
    yield
