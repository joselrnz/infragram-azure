"""Every frame draws the badge somebody decided it should.

A frame's title tab carries a small piece of vendor artwork. Which piece is
decided by the frame's *kind* and the theme's ``boundaries.icons`` map, and
until now nothing checked that map against anything. Two things had gone
wrong quietly.

An AWS account, an Auto Scaling group and the corporate datacenter drew the
generic tab even though the AWS deck ships a group box for each of them: the
artwork was in the tree and simply never wired up. And an Azure availability
zone drew the Availability Sets mark, which is a different construct -- a set
spreads across fault domains inside one datacenter, a zone is a separate
datacenter -- so the picture stated something false.

The rule is now written down: a frame's badge is the vendor's own artwork for
that boundary, and where the vendor ships none the frame takes the generic
tab. ``assets/catalog/frame-badges.json`` records every badge and every
blank with its reason, and this file fails when a theme disagrees with it.
"""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

import pytest

import infragram.nodes.frames as frames_package
from infragram.builders.architecture import load_icon_set, load_style

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
RECORD = ROOT / "skills/infragram-azure/assets/catalog/frame-badges.json"
VENDORS = ROOT / "skills/infragram-azure/assets/icons/vendors"


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))["libraries"]


def _theme_badges(group: str) -> dict[str, str]:
    return dict(load_style(group).cluster.icons or {})


def _kinds(group: str) -> set[str]:
    module = importlib.import_module(f"infragram.nodes.frames.{group}")
    return {
        cls.KIND
        for name in dir(module)
        if inspect.isclass(cls := getattr(module, name))
        and getattr(cls, "KIND", None)
        and getattr(cls, "FRAME_ID", None)
    }


def test_every_library_is_recorded() -> None:
    assert set(_record()) == set(frames_package.GROUPS)


@pytest.mark.parametrize("group", sorted(frames_package.GROUPS))
def test_the_record_covers_every_frame_kind(group: str) -> None:
    """Add a frame and this fails until its badge is decided either way."""
    entry = _record()[group]
    covered = set(entry.get("badges") or {}) | set(entry["blank"])
    assert covered == _kinds(group), sorted(covered ^ _kinds(group))


@pytest.mark.parametrize("group", sorted(frames_package.GROUPS))
def test_the_theme_matches_the_record(group: str) -> None:
    """The themes are what the renderers read; the record is the review."""
    assert _theme_badges(group) == dict(_record()[group].get("badges") or {})


@pytest.mark.parametrize("group", sorted(frames_package.GROUPS))
def test_every_blank_says_why(group: str) -> None:
    """A blank badge is a decision. An undecided one is a bug."""
    for kind, reason in _record()[group]["blank"].items():
        assert isinstance(reason, str) and len(reason) > 20, f"{group}.{kind}: {reason!r}"


@pytest.mark.parametrize("group", sorted(frames_package.GROUPS))
def test_every_badge_resolves_to_artwork_that_ships(group: str) -> None:
    """A reference that does not load leaves a frame silently unbranded."""
    for kind, reference in (_record()[group].get("badges") or {}).items():
        assert ":" in reference, f"{group}.{kind}: {reference}"
        collection, _, slug = reference.partition(":")
        pack = load_icon_set(collection)
        icon = pack[slug] if "#" in slug else pack.find(slug)
        assert icon.path.is_file(), f"{group}.{kind} -> {reference} has no file"


def test_azure_badges_are_the_decks_own_boundary_artwork() -> None:
    """Every Azure badge is an icon the Azure deck ships for that boundary,
    never a mark borrowed from a third-party logo pack, and the deck's own
    ids are the ones the record names."""
    catalog = json.loads((VENDORS / "azure" / "catalog.json").read_text(encoding="utf-8"))
    shipped = {i["id"] for i in catalog["icons"]}
    azure = _record()["azure"]
    assert azure.get("badges"), "Azure ships boundary artwork and must wear it"
    for kind, reference in azure["badges"].items():
        assert reference.startswith("azure:"), f"{kind} borrows {reference} from outside the deck"
        assert reference.partition(":")[2] in shipped, f"{kind} -> {reference} is not in the deck"
    for expected in (
        "subscriptions",
        "management-groups",
        "resource-groups",
        "virtual-networks",
        "subnet",
    ):
        assert expected in shipped, f"{expected} is no longer in the deck"


def test_the_azure_gallery_draws_both_subnets_without_leaving_it() -> None:
    """The gap that sent an Azure diagram into the core frames for a grey tab.

    Azure shipped one subnet frame and it was the private one, so a diagram
    with an internet-facing subnet reached for ``frames.generic.PublicSubnet``
    -- and a core frame keeps its own look wherever it is placed, by design.
    The picture came out with a grey bordered, grey badged subnet sitting
    between two Azure blue ones, which is not a style choice but a frame from
    the wrong gallery. Both kinds are Azure frames now.
    """
    assert {"subnet-private", "subnet-public"} <= _kinds("azure")


def test_both_azure_subnets_wear_the_decks_one_subnet_mark() -> None:
    """Azure ships a single Subnet icon and no public/private pair. A public
    subnet is a subnet -- the same boundary, differing in what routes to it --
    so the deck's own mark is that boundary's artwork, not a near-miss."""
    badges = _record()["azure"]["badges"]
    assert badges["subnet-private"] == badges["subnet-public"] == "azure:subnet"
    assert "subnet-public" in _record()["azure"].get("reasons", {})


def test_the_two_azure_subnets_are_told_apart_by_the_fill() -> None:
    """Sharing a mark must not make them the same picture: the private subnet
    keeps the filled interior it already had, the public one is left open."""
    cluster = load_style("azure").cluster
    assert cluster.colors["subnet-private"] == cluster.colors["subnet-public"]
    assert cluster.fills.get("subnet-private")
    assert not cluster.fills.get("subnet-public")


def test_the_kubernetes_cluster_wears_the_kubernetes_mark() -> None:
    """The one library whose cluster boundary is the platform itself."""
    kubernetes = _record()["kubernetes"]
    assert kubernetes["badges"] == {"cluster": "logos:kubernetes#mono"}
    assert "cluster" in kubernetes.get("reasons", {})


def test_an_availability_zone_never_borrows_the_availability_set_mark() -> None:
    """The specific falsehood this file was written after finding."""
    for group in frames_package.GROUPS:
        badges = _record()[group].get("badges") or {}
        assert "availability-set" not in str(badges.get("zone", "")), group
