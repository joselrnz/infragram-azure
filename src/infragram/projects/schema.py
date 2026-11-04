"""The JSON Schema of an ``.infragram.json`` document.

An editor that knows the schema completes keys, flags a misspelt one and
shows each field's description while the document is written by hand; VS
Code does it for any file whose ``$schema`` names the schema, or through its
``json.schemas`` setting, with no extension. The schema is generated from
the pydantic model the package validates with (``CloudProject``), so the two
cannot disagree: ``tests/unit/test_project_schema.py`` fails when the shipped
copy (``assets/schema/infragram-project.schema.json``) falls behind.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..paths import skill_assets
from .document import CloudProject

__all__ = ["SCHEMA_FILE", "project_schema", "schema_path", "schema_text"]

SCHEMA_FILE = "infragram-project.schema.json"


def schema_path() -> Path:
    """Where the shipped copy lives, in a checkout and in an installed wheel."""
    return skill_assets() / "schema" / SCHEMA_FILE


def project_schema() -> dict:
    """The document's JSON Schema (draft 2020-12), from the model."""
    schema = CloudProject.model_json_schema(mode="validation")
    ordered = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_FILE,
        "title": "Infragram Azure project",
        "description": "An .infragram.json document: the one source every export of a diagram is drawn from.",
    }
    defs = schema.pop("$defs", {})
    schema.pop("title", None)
    # A document may name this schema; the model accepts the key and ignores it.
    schema.setdefault("properties", {})["$schema"] = {
        "type": "string",
        "description": "The schema this document is written against, for an editor's completion.",
    }
    defs["CloudProject"] = schema
    # Documents of versions 1 and 2 are migrated when loaded (projects/
    # document.py); the schema describes version 3 and lets an older one be.
    defs["OlderVersion"] = {
        "type": "object",
        "description": "A version 1 or 2 document, migrated to version 3 when it is loaded.",
        "properties": {"schema_version": {"enum": [1, 2]}},
        "required": ["schema_version"],
    }
    return {
        **ordered,
        "anyOf": [{"$ref": "#/$defs/CloudProject"}, {"$ref": "#/$defs/OlderVersion"}],
        "$defs": defs,
    }


def schema_text() -> str:
    return json.dumps(project_schema(), indent=2, ensure_ascii=False) + "\n"
