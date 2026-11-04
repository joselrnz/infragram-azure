"""Azure prices read what a diagram's captions say.

A region frame often carries a note beside its name (``East US 2 ·
primary``), and a component's label often names its tier (``Azure Front
Door Premium``). Both are priced from the shipped table, with no network.
"""

from __future__ import annotations

import pytest

from infragram.author import Diagram
from infragram.nodes.azure import app_services, networking
from infragram.nodes.frames import azure
from infragram.pricing import price_project


def _priced(caption: str) -> dict:
    with Diagram("Region captions", slug="region-captions") as diagram:
        with azure.Subscription("Production"), azure.Region(caption):
            app_services.AppServices("App Service")
    project = diagram.to_project()
    result = price_project(project)
    assert result.priced, result.notes
    return project.topology.first(name="App Service").attributes["price"]


@pytest.mark.parametrize(
    ("caption", "region"),
    [
        ("East US 2", "eastus2"),
        ("East US 2 · primary", "eastus2"),
        ("Central US · standby", "centralus"),
        ("Region | West Europe", "westeurope"),
        ("UK South (DR)", "uksouth"),
    ],
)
def test_a_region_caption_with_a_note_prices_in_that_region(caption: str, region: str) -> None:
    price = _priced(caption)
    assert price["sizing"]["region"] == region
    assert "region" not in price["assumed"]


def test_a_caption_naming_no_region_is_still_refused() -> None:
    with Diagram("Region captions", slug="region-captions") as diagram:
        with azure.Subscription("Production"), azure.Region("Primary · standby"):
            app_services.AppServices("App Service")
    project = diagram.to_project()
    result = price_project(project)
    assert not result.priced
    assert any("Azure has no region 'primarystandby'" in note for note in result.notes)


def _front_door(name: str, **sizing: str) -> dict:
    with Diagram("Front Door", slug="front-door") as diagram:
        door = networking.FrontDoorAndCDNProfiles(name)
        if sizing:
            door.sizing(**sizing)
    project = diagram.to_project()
    result = price_project(project)
    assert result.priced, result.notes
    return project.topology.first(name=name).attributes["price"]


def test_front_door_takes_its_tier_from_the_label() -> None:
    price = _front_door("Azure Front Door Premium")
    assert price["sizing"]["tier"] == "Premium"
    assert "tier" not in price["assumed"]


def test_front_door_sizing_overrides_the_label() -> None:
    price = _front_door("Azure Front Door Premium", tier="Standard")
    assert price["sizing"]["tier"] == "Standard"


def test_front_door_without_a_tier_is_assumed_standard() -> None:
    price = _front_door("Azure Front Door")
    assert price["sizing"]["tier"] == "Standard"
    assert "tier" in price["assumed"]
