"""Checks that run against the newest Home Assistant, before there is a test plugin for it.

pytest-homeassistant-custom-component is released for each Home Assistant version a few days to
weeks after it, and the suite in tests/ needs it. These checks need only Home Assistant itself, so
CI runs them on the newest release and beta as soon as they are out. They cover what broke on
2026.11 (DeviceInfo became a dataclass without |) and what a release most often breaks: names the
integration imports.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from types import SimpleNamespace

import homeassistant  # noqa: F401 - imported first, as Home Assistant aliases httpx when it loads
import pytest

import custom_components.lk_ihc as lk_ihc
from custom_components.lk_ihc import entity
from custom_components.lk_ihc.project import parse_project

PROJECT = Path(__file__).parent.parent / "tests" / "fixtures" / "project.xml"


@pytest.mark.parametrize("name", [m.name for m in pkgutil.iter_modules(lk_ihc.__path__)])
def test_module_imports(name: str) -> None:
    """Every module imports, so nothing it takes from Home Assistant has moved or gone."""
    importlib.import_module(f"custom_components.lk_ihc.{name}")


def test_device_info_suggests_the_area(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each product's device info is built, and takes the area the installation already has."""
    monkeypatch.setattr(entity, "area_for_group", lambda hass, group: f"Area for {group}")
    connection = SimpleNamespace(serial_number="1062")
    resources = parse_project(PROJECT.read_text(encoding="utf-8")).resources
    assert resources
    for product, resource in resources:
        ihc_entity = entity.IHCEntity(connection, product, resource)
        ihc_entity.hass = object()
        info = ihc_entity.device_info
        assert info["identifiers"] == {("lk_ihc", f"1062-{product.product_id}")}
        if product.group:
            assert info["suggested_area"] == f"Area for {product.group}"
