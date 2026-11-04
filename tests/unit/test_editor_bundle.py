"""The editor's modules assemble into one page, and none is left out.

The chrome's stylesheets and the runtime's modules are separate files in the
repository and one document in the export. These pin the assembly: every
stylesheet under ``editor/ui`` has a place in the cascade order, every runtime
module is numbered once and names itself, and the page carries both whole.
"""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import indent

from infragram.editor import bundle
from infragram.exports import render_project_html
from infragram.exports.render import _scene_for
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
TEMPLATE = ROOT / "skills/infragram-azure/assets/templates/cloud/azure-aks-baseline.infragram.json"


def test_every_stylesheet_has_one_place_in_the_cascade() -> None:
    on_disk = sorted(path.relative_to(bundle.UI).as_posix() for path in bundle.UI.rglob("*.css"))
    assert sorted(bundle.STYLE_ORDER) == on_disk, (
        "add a new .css to bundle.STYLE_ORDER where it belongs"
    )
    assert len(set(bundle.STYLE_ORDER)) == len(bundle.STYLE_ORDER)
    # tokens come first, the overriding rails and responsive rules last
    assert bundle.STYLE_ORDER[0] == "styles/tokens.css"
    assert bundle.STYLE_ORDER[-2:] == ("styles/rails.css", "styles/responsive.css")


def test_runtime_modules_are_numbered_once_and_name_themselves() -> None:
    modules = bundle.runtime_modules()
    assert len(modules) >= 2
    numbers = [path.name.split("-", 1)[0] for path in modules]
    assert all(re.fullmatch(r"\d{2}", number) for number in numbers), numbers
    assert len(set(numbers)) == len(numbers), "two runtime modules share a number"
    for path in modules:
        header = path.read_text(encoding="utf-8").partition("\n")[0]
        assert header.startswith(f"// @module {path.stem}: "), (
            f"{path.name} must start with its @module line"
        )


def test_the_page_carries_the_whole_stylesheet_and_runtime() -> None:
    project = CloudProject.load(TEMPLATE)
    html = render_project_html(project)
    scene = _scene_for(project)
    runtime = bundle.runtime_script()
    assert indent(bundle.stylesheet(scene.width, scene.height), "    ") in html
    assert bundle.STAGE_WIDTH not in html and bundle.STAGE_HEIGHT not in html
    assert f"<script data-infragram-editor>\n{runtime}\n  </script>" in html
    assert "// @module" not in html, "module headers stay in the repository"
    # one closure: the first module opens it and the last closes it
    assert runtime.startswith("(async () => {") and runtime.rstrip().endswith("});")
    assert runtime.count("})().catch(error => {") == 1, (
        "startup failure handling closes the closure once"
    )
