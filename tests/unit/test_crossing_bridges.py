"""Bridge geometry must preserve endpoints and leave transparent underpasses."""

from __future__ import annotations

import pytest

from infragram.author import Diagram
from infragram.builders.crossings import crossing_plan
from infragram.builders.routing import Rect
from infragram.projects import Presentation


def test_static_and_browser_crossing_geometry_share_the_same_policy() -> None:
    import json
    import shutil
    import subprocess

    from infragram.builders import arrowheads, metrics
    from infragram.editor.bundle import RUNTIME

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to compare the two crossing implementations")
    source = (RUNTIME / "12-routing.js").read_text(encoding="utf-8")
    pure = source[source.index("  const crossingSegments") : source.index("  const applyCrossings")]
    cases = [
        {"wires": [("M20,100 L280,100", 1.4), ("M150,20 L150,260", 1.4)], "obstacles": []},
        {"wires": [("M400,100 H20", 2), ("M100,20 V260", 3), ("M250,20 V260", 1)], "obstacles": []},
        {
            "wires": [("M20,100 H280", 1.4), ("M150,20 V260", 1.4)],
            "obstacles": [Rect(142, 80, 158, 93)],
        },
        {
            "wires": [("M20,100 H280", 1.4), ("M150,20 V260", 1.4), ("M20,92 H280", 1.4)],
            "obstacles": [],
        },
        {
            "wires": [
                ("M20,100 L40,100 Q48,100 48,108 L48,160 L280,160", 1.4),
                ("M150,20 L150,260", 1.4),
            ],
            "obstacles": [],
        },
    ]
    expected = []
    payload = []
    for case in cases:
        paths, masks, counts = crossing_plan(case["wires"], case["obstacles"])
        expected.append(
            {
                "paths": paths,
                "masks": {str(k): v for k, v in masks.items()},
                "counts": {str(k): v for k, v in counts.items()},
            }
        )
        payload.append(
            {"wires": case["wires"], "obstacles": [vars(box) for box in case["obstacles"]]}
        )
    pure = "const ARROWHEADS=" + json.dumps({"shaft": arrowheads.shaft()}) + ";\n" + pure
    script = (
        "const METRICS="
        + json.dumps(metrics.spec())
        + ";\n"
        + pure
        + "\n"
        + """
      let input=''; process.stdin.on('data',part=>input+=part);
      process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(input).map(item=>{
        const plan=crossingPlan(item.wires,item.obstacles);
        return {paths:plan.paths,masks:Object.fromEntries(plan.masks),counts:Object.fromEntries(plan.counts)};
      }))));
    """
    )
    result = subprocess.run(
        [node, "-e", script], input=json.dumps(payload), capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout) == json.loads(json.dumps(expected))


@pytest.mark.parametrize("horizontal", ["M20,100 L280,100", "M280,100 H20"])
def test_a_crossing_hops_up_in_both_directions(horizontal: str) -> None:
    paths, masks, counts = crossing_plan([(horizontal, 1.4), ("M150,20 V260", 1.4)])
    assert "A8,8" in paths[0]
    assert paths[1] == "M150,20 V260"
    assert masks == {1: [(150, 92, 2.5)]}
    assert counts == {0: 1}
    assert paths[0].startswith(horizontal.split()[0])
    assert paths[0].strip().endswith("L280,100" if "M20" in horizontal else "L20,100")


@pytest.mark.parametrize(
    "other",
    [
        "M150,100 L150,260",  # a touching endpoint
        "M150,20 L150,100",  # a touching endpoint in the other direction
        "M25,20 L25,260",  # insufficient room before the arrowhead/bend
        "M37,20 L37,260",  # keep the arrowhead's straight shaft intact
        "M150,20 L250,260",  # a diagonal is not a perpendicular crossing
        "M20,100 L280,100",  # shared run, not an intersection
    ],
)
def test_touching_overlapping_and_short_runs_are_not_bridges(other: str) -> None:
    wires = [("M20,100 L280,100", 1.4), (other, 1.4)]
    paths, masks, counts = crossing_plan(wires)
    assert paths == [path for path, _ in wires]
    assert not masks and not counts


def test_a_bridge_cannot_enter_a_caption_or_node_box() -> None:
    wires = [("M20,100 L280,100", 1.4), ("M150,20 L150,260", 1.4)]
    paths, masks, counts = crossing_plan(wires, [Rect(142, 80, 158, 93)])
    assert paths == [path for path, _ in wires]
    assert not masks and not counts


def test_a_nearby_parallel_wire_does_not_become_a_junction() -> None:
    wires = [("M20,100 L280,100", 1.4), ("M150,20 L150,260", 1.4), ("M20,92 L280,92", 1.4)]
    # The lower wire cannot jump into the upper one. The upper wire may
    # safely jump away from it, with its own isolated underpass.
    assert 0 not in crossing_plan(wires)[2]


def test_multiple_spaced_crossings_have_ordered_bridges_and_separate_masks() -> None:
    paths, masks, counts = crossing_plan(
        [
            ("M400,100 L20,100", 1.4),
            ("M100,20 L100,260", 1.4),
            ("M250,20 L250,260", 1.4),
        ]
    )
    assert counts == {0: 2}
    assert paths[0].index("L258,100") < paths[0].index("L108,100")
    assert set(masks) == {1, 2}


def test_crossings_are_validated_in_sources_and_default_to_plain_for_old_documents() -> None:
    assert Presentation().crossings == "plain"
    assert Diagram("Network", crossings="bridge").crossings == "bridge"
    with pytest.raises(ValueError):
        Presentation(crossings="junction")
    with pytest.raises(ValueError):
        Diagram("Network", crossings="junction")
