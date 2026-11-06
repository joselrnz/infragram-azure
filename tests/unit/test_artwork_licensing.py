"""How we came by each piece of artwork, recorded and enforced.

Every icon in the index carries a ``license_status``. Until now that field
was the literal string ``"provider-terms"`` on all 2,617 vendor icons, which
said nothing at all: the on-premises set comes from an MIT upstream with a
per-file hash, AWS ships an asset pack whose own terms permit diagram use,
and two libraries were fetched off a vendor web page with no grant ever
established. One label for all three hid the only distinction that matters
before publishing a repository under MIT.

The status is now derived from ``license_basis`` in the provider registry,
and this file is what stops it drifting back. The count of unverified artwork
is pinned deliberately: it may shrink, and it must never grow by accident.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from infragram.builders.index import build_index, license_bases

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
PROVIDERS = ROOT / "skills/infragram-azure/assets/catalog/providers.json"

#: Every basis a collection may declare, and what each one means.
RECOGNISED = {
    "upstream-permissive",  # an OSS licence grants redistribution
    "provider-terms",  # the vendor's asset pack permits diagram use
    "permissive",  # a CC0/MIT logo set
    "vendor-unverified",  # fetched from a vendor page; no grant established
    "no-artwork",  # a preview registration: frames and theme only
    "original-artwork",  # tiles drawn for this project from MIT glyphs; not the vendor's icons
}

#: Libraries whose artwork carries no established redistribution grant, and
#: how many icons that is. This edition ships none: Azure's artwork is under
#: Microsoft's architecture-icon terms and Kubernetes' under Apache-2.0. The
#: number is pinned at zero so it cannot grow without somebody deciding to.
UNVERIFIED: set[str] = set()
UNVERIFIED_ICONS = 0


def _providers() -> list[dict]:
    return json.loads(PROVIDERS.read_text(encoding="utf-8"))["providers"]


def test_every_library_declares_how_we_came_by_its_artwork() -> None:
    """A library with no declared basis is the bug this field exists to catch."""
    missing = [p["id"] for p in _providers() if not p.get("license_basis")]
    assert missing == [], f"no licence basis recorded for {missing}"
    unknown = {
        p["id"]: p["license_basis"] for p in _providers() if p["license_basis"] not in RECOGNISED
    }
    assert unknown == {}, unknown


def test_the_index_carries_the_basis_rather_than_a_constant() -> None:
    """The regression this replaced: one hard-coded label on everything."""
    _, index = build_index()
    seen = Counter(icon.get("license_status") for icon in index["icons"])
    assert "unrecorded" not in seen, "a collection reached the index with no basis"
    assert set(seen) <= RECOGNISED, sorted(set(seen) - RECOGNISED)
    # More than one value, which is the whole point of the change: the two
    # libraries came by their artwork differently, and the logo set a third way.
    assert {"provider-terms", "upstream-permissive"} <= set(seen), dict(seen)
    assert len(seen) >= 3, f"the field is uniform again: {dict(seen)}"


def test_unverified_artwork_is_exactly_what_we_know_about() -> None:
    """It may shrink. It must never grow without somebody deciding to."""
    _, index = build_index()
    unverified = [i for i in index["icons"] if i.get("license_status") == "vendor-unverified"]
    libraries = {str(i["source"]).split(":")[-1] for i in unverified}
    assert libraries == UNVERIFIED, f"the unverified set moved: {sorted(libraries)}"
    assert len(unverified) == UNVERIFIED_ICONS, (
        f"{len(unverified)} unverified icons, expected {UNVERIFIED_ICONS}; "
        "if artwork was cleared or removed, update the number and say why"
    )


@pytest.mark.parametrize(
    "provider,expected",
    [
        ("kubernetes", "upstream-permissive"),
        ("azure", "provider-terms"),
    ],
)
def test_a_library_claims_only_what_it_has(provider: str, expected: str) -> None:
    """Each shipped library's basis, pinned so neither drifts into another."""
    assert license_bases()[provider] == expected


def test_a_preview_library_ships_no_vendor_artwork() -> None:
    """`no-artwork` is a claim about the tree, so check the tree."""
    vendors = ROOT / "skills/infragram-azure/assets/icons/vendors"
    for record in _providers():
        if record.get("license_basis") != "no-artwork":
            continue
        catalog = vendors / record["id"] / "catalog.json"
        assert not catalog.is_file(), (
            f"{record['id']} says it ships no artwork but {catalog.name} exists"
        )


def test_the_gallery_ships_nothing_it_cannot_redistribute() -> None:
    """Five glyphs were once fetched from a vendor page and said so.

    No licence-clean brand mark exists for Apache Hop, Pentaho, Dagster, SAS
    or Stata, so each carries a generic glyph instead of a logo we had no
    right to ship. Nothing in the gallery may carry that warning again.
    """
    gallery = (ROOT / "skills/infragram-azure/references/primitive-icons.md").read_text(
        encoding="utf-8"
    )
    flagged = [
        line
        for line in gallery.splitlines()
        if line.startswith("Source: ") and "verify license" in line.lower()
    ]
    assert flagged == [], flagged
    assert "Direct fetch /" not in gallery, "a glyph is sourced from a vendor page again"


def _official_logos() -> dict[str, dict[str, str]]:
    """The OFFICIAL table of scripts/build/icons.py, read without running it."""
    import ast

    source = (ROOT / "scripts/build/icons.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "OFFICIAL":
            assert node.value is not None
            table = ast.literal_eval(node.value)
            assert isinstance(table, dict)
            return table
    raise AssertionError("scripts/build/icons.py has no OFFICIAL table")


def test_every_project_logo_is_pinned_kept_and_accounted_for() -> None:
    """A logo taken from a project's own repository is the exception the
    gallery allows, and only with its paper trail: a pinned commit, the
    unmodified file kept beside the others, its entry in
    THIRD_PARTY_LICENSES.md, and the gallery naming where it came from."""
    logos = _official_logos()
    assert logos, "no project logos: drop this test with the table"
    notices = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    gallery = (ROOT / "skills/infragram-azure/references/primitive-icons.md").read_text(
        encoding="utf-8"
    )
    for slot, entry in logos.items():
        assert len(entry["commit"]) == 40, f"{slot}: pin a full commit, not a branch"
        assert (ROOT / "scripts/vendor/icons/official" / f"{slot}.svg").is_file(), slot
        assert entry["commit"] in notices and entry["path"] in notices, (
            f"{slot} is not recorded in THIRD_PARTY_LICENSES.md"
        )
        assert f"`{entry['repository']}` `{entry['path']}`" in gallery, slot
    # a permissive logo ships its notice; one without a grant says so
    assert (ROOT / "licenses/valkey.txt").is_file()
    assert "Rights status:** Redpanda" in notices
