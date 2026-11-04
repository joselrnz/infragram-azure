#!/usr/bin/env python3
"""Contract for the catalog-generated node classes.

Build scripts name services as classes rather than SVG paths, so what needs
guarding is the generation itself: that a class exists for a real icon and
carries its artwork, that a typo fails loudly at build time instead of
silently dropping an icon, and that nesting stays unlimited.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))

from infragram.builders.architecture import icon_for  # noqa: E402
from infragram.nodes import Group, azure, logos, reset_ids  # noqa: E402
from infragram.nodes.azure import compute  # noqa: E402


def test_class_carries_its_icon() -> None:
    """A generated class resolves artwork with no IconSet passed in."""
    element = azure.KubernetesServices("AKS", "private cluster")
    icon = icon_for(element)
    if icon is None:
        raise AssertionError("azure.KubernetesServices resolved no icon")
    if not icon.path.is_file():
        raise AssertionError(f"icon file missing: {icon.path}")
    if element.attributes["detail"] != "private cluster":
        raise AssertionError("positional detail was not stored")
    print(f"OK: azure.KubernetesServices -> {icon.path.name}")


def test_unknown_class_fails_loudly() -> None:
    """A mistyped service is an error, not a missing icon in the output."""
    try:
        azure.KubernetesServicez  # noqa: B018
    except AttributeError as exc:
        if "KubernetesServices" not in str(exc):
            raise AssertionError(f"no near-match suggested: {exc}") from exc
        print("OK: unknown class raises AttributeError suggesting the real name")
        return
    raise AssertionError("a nonexistent class did not raise")


def test_collections_mix_in_one_tree() -> None:
    """Vendor artwork and brand logos coexist; each keeps its own pack."""
    zone = Group("Edge", "vnet")
    zone >> azure.Firewalls("Azure Firewall", "egress")
    zone >> logos.Nginx("Ingress", "TLS termination")
    packs = {child.attributes.get("collection") for child in zone.children}
    if packs != {"azure", "logos"}:
        raise AssertionError(f"expected both packs, got {packs}")
    for child in zone.children:
        if icon_for(child) is None:
            raise AssertionError(f"{child.name} lost its icon when mixed")
    print("OK: azure and logos resolve side by side in one tree")


def test_auto_ids_stay_unique() -> None:
    """Repeated names must not collide - two regions both run a Bastion."""
    reset_ids()
    estate = Group("Estate", "subscription")
    for letter in ("A", "B"):
        region = Group(f"Region {letter}", "region")
        region >> azure.Bastions("Azure Bastion", "operator access")
        estate.add(region)
    ids = [element.id for element in estate.walk()]
    if len(ids) != len(set(ids)):
        raise AssertionError(f"duplicate ids generated: {ids}")
    print(f"OK: {len(ids)} auto ids unique across repeated names")


def test_nesting_is_unlimited() -> None:
    """Depth is bounded by nothing in the model; >> also branches."""
    reset_ids()
    root = Group("L0", "group")
    cursor = root
    for level in range(1, 12):
        cursor = cursor >> Group(f"L{level}", "group")
    if root.depth() != 12:
        raise AssertionError(f"expected depth 12, got {root.depth()}")

    reset_ids()
    vnet = Group("VNet", "vnet")
    for index in (1, 2):
        subnet = vnet >> Group(f"Subnet {index}", "subnet")
        subnet >> azure.VirtualMachine(f"VM {index}", "workload")
    if len(vnet.children) != 2:
        raise AssertionError(f"branching lost siblings: {len(vnet.children)}")
    print("OK: 12-level chain and sibling branching both hold")


def test_inheritance_chain_carries_identity() -> None:
    """Collection and category come from the bases, not from the leaf."""
    vm = compute.VirtualMachine
    if (vm.COLLECTION, vm.CATEGORY) != ("azure", "compute"):
        raise AssertionError(f"wrong identity: {vm.COLLECTION}/{vm.CATEGORY}")
    chain = [c.__name__ for c in vm.__mro__]
    for expected in ("VirtualMachine", "_Compute", "_Azure", "Element"):
        if expected not in chain:
            raise AssertionError(f"{expected} missing from {chain[:5]}")
    made = vm("Web tier", "3 instances")
    if made.attributes["category"] != "compute":
        raise AssertionError("instance lost its category")
    print(f"OK: {' <- '.join(chain[:4])}")


def test_nested_clusters_differ_by_depth() -> None:
    """Deep nesting must read; identical borders at every level do not."""
    from infragram.builders.architecture import from_topology
    from infragram.themes import Theme

    reset_ids()
    root = Group("Tenant", "tenant")
    cursor = root
    for _level, label in enumerate(("Region", "Zone", "VNet", "Subnet")):
        cursor = cursor >> Group(label, label.lower())
    cursor >> compute.VirtualMachine("Host", "workload")

    theme = Theme.from_colors(
        {
            "paper": "#0f1720",
            "paper_2": "#162635",
            "ink": "#f5f9fd",
            "muted": "#bfceda",
            "soft": "#8aa4b8",
            "accent": "#50a7e8",
            "link": "#78bced",
        }
    )
    scene = from_topology(root, theme, slug="depth", title="t", desc="d")
    drawn = [c for c in scene.root.clusters() if c is not scene.root and c.label]
    depths = [c.depth for c in drawn]
    if depths != sorted(set(depths)) or min(depths) != 0:
        raise AssertionError(f"depths not a clean 0..n chain: {depths}")
    borders = {scene.style.cluster.border_at(c.depth) for c in drawn}
    if len(borders) != len(drawn):
        raise AssertionError(f"{len(drawn)} nested clusters share {len(borders)} border alphas")
    print(f"OK: {len(drawn)} nesting levels -> {len(borders)} distinct border alphas")


def test_accent_precedence() -> None:
    """Call site beats class, class beats skin, skin beats nothing."""
    from infragram.builders.architecture import accent_for
    from infragram.builders.scene import Style
    from infragram.nodes.logos import software

    skin = Style()
    skin.node.accent_roles = {"databases": "link", "azure": "soft"}

    cases = [
        (software.Nginx("Ingress"), "#009639", "class BRAND from the catalog"),
        (compute.VirtualMachine("Web", accent="accent"), "accent", "call site"),
        (compute.VirtualMachine("Box"), "soft", "skin collection map"),
        (Group("Zone", "vnet"), "", "nothing set"),
    ]
    for element, expected, why in cases:
        got = accent_for(element, skin)
        if got != expected:
            raise AssertionError(f"{why}: expected {expected!r}, got {got!r}")
    print(f"OK: accent precedence holds across {len(cases)} channels")


def test_fit_frames_the_outermost_layout() -> None:
    """canvas.fit tightens to content instead of holding the 1200 floor."""
    from infragram.builders.architecture import from_topology
    from infragram.builders.scene import Style
    from infragram.themes import Theme

    reset_ids()
    root = Group("Small", "group")
    zone = root >> Group("Zone", "vnet")
    zone >> compute.VirtualMachine("Only host", "one box")

    theme = Theme.from_colors(
        {
            "paper": "#0f1720",
            "paper_2": "#162635",
            "ink": "#f5f9fd",
            "muted": "#bfceda",
            "soft": "#8aa4b8",
            "accent": "#50a7e8",
            "link": "#78bced",
        }
    )
    loose = from_topology(root, theme, slug="a", title="t", desc="d")
    tight_style = Style()
    tight_style.canvas.fit = True
    tight = from_topology(root, theme, slug="b", title="t", desc="d", style=tight_style)

    if loose.width != 1200:
        raise AssertionError(f"default should hold the gallery floor, got {loose.width}")
    if tight.width >= loose.width:
        raise AssertionError(f"fit did not tighten: {tight.width} vs {loose.width}")
    drawn = [c for c in tight.root.clusters() if c is not tight.root and c.label]
    left = min(c.x for c in drawn)
    right = tight.width - max(c.x + c.width for c in drawn)
    if abs(left - right) > 1:
        raise AssertionError(f"fit is not centred: {left} left vs {right} right")
    print(f"OK: fit {loose.width} -> {tight.width}, centred within 1px")


def test_unknown_link_target_is_an_error() -> None:
    """A link to an id that is not in the tree must not vanish quietly.

    .to() captures the target's id at call time. If the variable is later
    reassigned to a fresh node, the captured id no longer resolves -- and
    the link was simply dropped, losing a fact the author had stated.
    """
    from infragram.builders.architecture import from_topology
    from infragram.nodes.azure import compute
    from infragram.themes import Theme

    theme = Theme.from_colors(
        {
            "paper": "#0f1720",
            "paper_2": "#162635",
            "ink": "#f5f9fd",
            "muted": "#bfceda",
            "soft": "#8aa4b8",
            "accent": "#50a7e8",
            "link": "#78bced",
        }
    )

    reset_ids()
    root = Group("Estate", "subscription")
    zone = root >> Group("Zone", "vnet")
    source = compute.VirtualMachine("Source", "one")
    stale = compute.VirtualMachine("Stale", "never added")
    zone >> source
    source.to(stale, kind="solid")  # target is not in the tree

    try:
        from_topology(root, theme, slug="orphan", title="t", desc="d")
    except ValueError as exc:
        if "unknown id" not in str(exc):
            raise AssertionError(f"unhelpful message: {exc}") from exc
        print("OK: a link to a missing node raises instead of disappearing")
        return
    raise AssertionError("a dangling link was accepted silently")


def test_frames_and_shared_primitives_are_classes() -> None:
    """The frame gallery and the shared library are generated classes too."""
    from infragram.nodes import Frame, infragram as shared
    from infragram.nodes.frames import azure, generic

    vnet = azure.VNet("vnet-prod 10.10.0.0/16")
    if not isinstance(vnet, Frame) or not vnet.is_frame:
        raise AssertionError("frames.azure.VNet should be an empty-but-still-a-frame element")
    if vnet.component is None or vnet.component.icon_ref != "infragram:custom-boundary-azure-vnet":
        raise AssertionError(f"frame lost its gallery id: {vnet.component}")
    if vnet.attributes.get("editor_frame_group") != "azure" or vnet.type != "network":
        raise AssertionError(f"frame lost its group or kind: {vnet.attributes} {vnet.type}")
    dmz = generic.DMZ("Perimeter", flow="row")
    if dmz.type != "dmz" or dmz.attributes.get("flow") != "row":
        raise AssertionError("generic.DMZ should be a dmz frame with a row flow")
    mainframe = shared.compute.Mainframe("IBM z16", "z/OS")
    if (
        mainframe.attributes.get("collection") != "infragram"
        or mainframe.attributes.get("icon") != "mainframe"
    ):
        raise AssertionError(f"shared primitive lost its identity: {mainframe.attributes}")
    print("OK: frames and shared primitives are generated classes")


def main() -> int:
    test_class_carries_its_icon()
    test_unknown_class_fails_loudly()
    test_collections_mix_in_one_tree()
    test_auto_ids_stay_unique()
    test_nesting_is_unlimited()
    test_inheritance_chain_carries_identity()
    test_nested_clusters_differ_by_depth()
    test_accent_precedence()
    test_fit_frames_the_outermost_layout()
    test_unknown_link_target_is_an_error()
    test_frames_and_shared_primitives_are_classes()
    print("PASS: node class contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
