"""Component search works with only this edition's installed libraries."""

from __future__ import annotations

import json

from infragram.catalog.find import find_patterns, libraries, pattern_classes
from infragram.cli.user.find import main
from infragram.mcp.run import _run
from infragram.mcp.tools import _BY_NAME


def test_cli_finds_aks_without_loading_omitted_vendor_patterns(capsys) -> None:
    assert main(["aks", "--json"]) == 0
    matches = json.loads(capsys.readouterr().out)
    assert any(
        match["library"] == "azure" and match["class"] == "KubernetesServices" for match in matches
    )
    assert not any("infragram.nodes.aws" in match["import"] for match in matches)


def test_mcp_uses_the_same_azure_component_search() -> None:
    result = _run(_BY_NAME["find_components"], {"query": "aks", "library": "azure"})
    assert not result.failed, result.text
    assert any("KubernetesServices" in match["import"] for match in result.data["matches"])


def test_only_installed_libraries_and_generic_patterns_are_advertised() -> None:
    known = {library.id for library in libraries()}
    assert {"azure", "kubernetes", "databricks"} <= known
    assert not {"aws", "gcp", "onprem"}.intersection(known)
    assert not any(hit.module.endswith((".aws", ".hybrid")) for hit in pattern_classes())
    assert find_patterns("MultiAZ") == []
    assert find_patterns("DirectConnectUplink") == []
    assert find_patterns("Blueprint")
