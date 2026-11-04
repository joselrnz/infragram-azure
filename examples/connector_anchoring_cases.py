"""The connector anchoring cases as small diagrams, one project each.

The same five cases the reference drawing shows (``connector-anchors-cases.svg``)
and the checker test composes, exported through the real pipeline so the
pictures can be looked at rather than imagined: glyphs side by side, glyphs
stacked, a card to a glyph, a wire passing a third node, and many wires on
one side of a glyph. Every wire end meets its node at the card's edge or at
the glyph's own edge or the caption's underside -- the shipped checker
enforces it on these exports the same as on any other.

Run from any directory::

    PYTHONPATH="<plugin root>/src" python examples/connector_anchoring_cases.py

which writes ``dist/anchoring-cases/<case>.html|svg|png`` for the five cases.
``infragram compose`` on this file exports the five cases in one picture,
each in its own frame.
"""

from __future__ import annotations

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.nodes import infragram as shared
from infragram.nodes.azure import compute, general, identity
from infragram.nodes.frames import azure as frames, generic


def side_by_side() -> Diagram:
    with Diagram(
        "Glyphs side by side",
        "Sides face the other end, at the glyph's middle.",
        slug="anchoring-side-by-side",
    ) as diagram:
        internet = shared.networking.PublicInternet("Internet", "public")
        browser = general.Browser("Browser", "client")
        internet >> Edge("egress") >> browser
    return diagram


def stacked() -> Diagram:
    with Diagram(
        "Glyphs stacked",
        "Leaves under the caption, meets the glyph's top.",
        slug="anchoring-stacked",
    ) as diagram:
        with frames.Subscription("Stacked").column():
            users = shared.identity.PublicUsers("Users", "people")
            balancer = shared.networking.GenericLoadBalancer("Load balancer", "L7")
        users >> Edge("HTTPS") >> balancer
    return diagram


def card_to_glyph() -> Diagram:
    with Diagram(
        "Card to glyph",
        "A card's edge to a glyph's edge; the air beside the glyph is free.",
        slug="anchoring-card-to-glyph",
    ) as diagram:
        with (
            frames.Subscription("Production"),
            frames.ResourceGroup("rg-prod"),
            frames.VNet("VNet"),
        ):
            with frames.Subnet("Private"):
                app = compute.VirtualMachine("App servers", "scale set")
            with frames.Subnet("Management"):
                operators = identity.Users("Operators", "Bastion")
        app >> Edge("SSH") >> operators
    return diagram


def passing_a_third_node() -> Diagram:
    with Diagram(
        "Passing a third node",
        "Other nodes block their whole box, caption included.",
        slug="anchoring-passing-a-third-node",
    ) as diagram:
        with frames.Subscription("Row").row():
            client = shared.identity.PublicUsers("Client", "browser")
            shared.security.Firewall("Bastion", "jump host")
            api = compute.FunctionApps("API", "REST")
        client >> Edge("HTTPS") >> api
    return diagram


def many_wires_one_side() -> Diagram:
    with Diagram(
        "Many wires on one side",
        "Every wire on a side meets at the glyph's one point on that side.",
        slug="anchoring-many-wires",
    ) as diagram:
        hub = shared.networking.CoreSwitch("Core switch", "spine")
        leaves = [shared.networking.AccessSwitch(f"Leaf {n}", "access") for n in (1, 2, 3, 4)]
        hub >> Edge() >> leaves
    return diagram


CASES = (side_by_side, stacked, card_to_glyph, passing_a_third_node, many_wires_one_side)


def build_all() -> list[Diagram]:
    return [case() for case in CASES]


# What the compose runner exports when given this file: the five cases in one
# picture, each in its own frame. Run the file directly for five separate
# pictures.
with Diagram(
    "Connector anchoring cases",
    "The five drawn anchoring cases in one picture, each in its own frame.",
    slug="connector-anchoring-cases",
) as diagram:
    with generic.Environment("Connector anchoring cases").column():
        with generic.Environment("Side by side").row():
            internet = shared.networking.PublicInternet("Internet", "public")
            browser = general.Browser("Browser", "client")
        internet >> Edge("egress") >> browser

        with generic.Environment("Stacked").column():
            users = shared.identity.PublicUsers("Users", "people")
            balancer = shared.networking.GenericLoadBalancer("Load balancer", "L7")
        users >> Edge("HTTPS") >> balancer

        with (
            frames.Subscription("Card to glyph"),
            frames.ResourceGroup("rg-prod"),
            frames.VNet("VNet"),
        ):
            with frames.Subnet("Private"):
                app = compute.VirtualMachine("App servers", "scale set")
            with frames.Subnet("Management"):
                operators = identity.Users("Operators", "Bastion")
        app >> Edge("SSH") >> operators

        with generic.Environment("Passing a third node").row():
            client = shared.identity.PublicUsers("Client", "browser")
            shared.security.Firewall("Bastion", "jump host")
            api = compute.FunctionApps("API", "REST")
        client >> Edge("HTTPS") >> api

        with generic.Environment("Many wires on one side").row():
            hub = shared.networking.CoreSwitch("Core switch", "spine")
            leaves = [shared.networking.AccessSwitch(f"Leaf {n}", "access") for n in (1, 2, 3, 4)]
        hub >> Edge() >> leaves


if __name__ == "__main__":
    out = Path("dist") / "anchoring-cases"
    for case in build_all():
        result = case.export(out, display="card", overwrite=True)
        print(result.png)
