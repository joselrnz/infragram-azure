"""The comments file (ADR 0009): what it holds, where it is found, what the
checker says about it, and that only the page carries it."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from infragram.exports import render_project_html
from infragram.projects import CloudProject
from infragram.projects.comments import Comments, find_comments, page_comments

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


def load_template_project(name: str) -> CloudProject:
    (path,) = (ROOT / "skills").glob(f"*/assets/templates/cloud/{name}.infragram.json")
    return CloudProject.load(path)


def _checker():
    path = next(ROOT.glob("skills/*/scripts/project_check.py"))
    spec = importlib.util.spec_from_file_location("_project_check_comments", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _file(slug: str = "review", **comment) -> dict:
    return {
        "format": "infragram.comments/1",
        "slug": slug,
        "comments": [
            {
                "id": "c-abc123",
                "anchor": {"kind": "node", "id": "vm-app", "name": "vm-app"},
                "author": "Ana",
                "text": "Is this VM still needed?",
                "at": "2026-11-06T10:00:00Z",
                **comment,
            }
        ],
    }


def test_a_file_reads_and_anything_else_is_refused() -> None:
    comments = Comments.model_validate(_file())
    assert comments.comments[0].anchor.kind == "node"
    for bad in (
        {"text": ""},
        {"id": "nope"},
        {"anchor": {"kind": "layer", "id": "x"}},
        {"extra": 1},
    ):
        with pytest.raises(ValidationError):
            Comments.model_validate(_file(**bad))


def test_the_file_is_found_beside_the_document_and_must_be_about_it(tmp_path: Path) -> None:
    assert find_comments(tmp_path, "review") is None
    (tmp_path / "review.comments.json").write_text(json.dumps(_file()), encoding="utf-8")
    found = find_comments(tmp_path, "review")
    assert found is not None and len(found.comments) == 1
    (tmp_path / "other.comments.json").write_text(json.dumps(_file("review")), encoding="utf-8")
    with pytest.raises(ValueError, match="holds comments on 'review', not 'other'"):
        find_comments(tmp_path, "other")


def test_only_the_page_carries_them_and_reads_them_back() -> None:
    project = load_template_project("azure-web-app-front-door")
    comments = Comments.model_validate(_file(project.slug))
    bare = render_project_html(project)
    page = render_project_html(project, comments=comments)
    assert page_comments(bare) is None
    assert 'id="infragram-comments"' not in bare
    carried = page_comments(page)
    assert carried is not None and carried.comments[0].text == "Is this VM still needed?"
    # a comment that spells a closing tag cannot end the script that carries it
    sly = Comments.model_validate(_file(project.slug, text="</script><script>alert(1)</script>"))
    page = render_project_html(project, comments=sly)
    assert "</script><script>alert(1)" not in page
    assert page_comments(page).comments[0].text.startswith("</script>")


def test_the_checker_reads_a_comments_file_and_a_page_s_comments(tmp_path: Path) -> None:
    checker = _checker()
    good = tmp_path / "review.comments.json"
    good.write_text(json.dumps(_file()), encoding="utf-8")
    ok, message = checker.check_path(good)
    assert ok, message
    assert "comments on review - 1 comment(s)" in message
    bad = tmp_path / "bad.comments.json"
    bad.write_text(json.dumps(_file(anchor={"kind": "layer", "id": ""})), encoding="utf-8")
    ok, message = checker.check_path(bad)
    assert not ok and "anchor.kind must be node, boundary or edge" in message
    project = load_template_project("azure-web-app-front-door")
    page = tmp_path / "page.html"
    page.write_text(
        render_project_html(project, comments=Comments.model_validate(_file(project.slug))),
        encoding="utf-8",
    )
    ok, message = checker.check_path(page)
    assert ok, message
