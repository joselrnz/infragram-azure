"""Regeneration keeps each output's existing LF or CRLF convention."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from infragram.builders.index import build_index

ROOT = Path(__file__).resolve().parents[2]


def _script(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("newline", (b"\n", b"\r\n"))
def test_node_regeneration_keeps_existing_endings_and_new_files_are_lf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, newline: bytes
) -> None:
    generator = _script("scripts/tools/generate-nodes.py", "node_newlines")
    out = tmp_path / "nodes"
    package = out / "azure"
    package.mkdir(parents=True)
    existing = package / "compute.py"
    existing.write_bytes(b"old" + newline)
    new = package / "new.py"
    text = "# café\nclass _Azure:\n    pass\n\nclass VM(_Azure):\n    pass\n"
    monkeypatch.setattr(generator, "OUT", out)
    monkeypatch.setattr(generator, "plan", lambda: {existing: text, new: text})
    monkeypatch.setattr(sys, "argv", ["generate-nodes"])
    assert generator.main() == 0
    expected = text.encode("utf-8").replace(b"\n", newline)
    assert existing.read_bytes() == expected
    assert new.read_bytes() == text.encode("utf-8")
    assert generator.main() == 0 and existing.read_bytes() == expected
    monkeypatch.setattr(sys, "argv", ["generate-nodes", "--check"])
    assert generator.main() == 0


@pytest.mark.parametrize("newline", (b"\n", b"\r\n"))
def test_inventory_regeneration_preserves_each_text_outputs_endings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, newline: bytes
) -> None:
    builder = _script("scripts/inventory/build.py", "inventory_newlines")
    inventory, problems = builder.build_inventory()
    assert not problems
    outputs = {
        "JSON_PATH": (tmp_path / "inventory.json", builder.serialize(inventory)),
        "MARKDOWN_PATH": (tmp_path / "inventory.md", builder.render_markdown(inventory)),
        "SHARED_PATH": (tmp_path / "shared.md", builder.render_shared_components(inventory)),
        "DOCS_MARKDOWN_PATH": (
            tmp_path / "docs" / "README.md",
            builder.render_docs_markdown(inventory),
        ),
    }
    for name, (path, _text) in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old" + newline)
        monkeypatch.setattr(builder, name, path)
    monkeypatch.setattr(builder, "DOCS", tmp_path / "docs")
    monkeypatch.setattr(builder, "load_payload", lambda: (None, None))
    monkeypatch.setattr(builder, "build_inventory", lambda loaded: (inventory, []))
    assert builder.main([]) == 0
    before = {}
    for path, text in outputs.values():
        before[path] = path.read_bytes()
        assert before[path] == text.encode("utf-8").replace(b"\n", newline)
    assert builder.main([]) == 0
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("newline", (b"\n", b"\r\n"))
def test_icon_index_regeneration_preserves_existing_endings(tmp_path: Path, newline: bytes) -> None:
    path = tmp_path / "index.json"
    path.write_bytes(b"old" + newline)
    written, index = build_index(path)
    assert written == path
    expected = (json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    assert path.read_bytes() == expected.replace(b"\n", newline)
    before = path.read_bytes()
    build_index(path)
    assert path.read_bytes() == before
