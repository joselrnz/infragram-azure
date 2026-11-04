"""Building the price tables from each cloud's public price source.

``scripts/build/price-tables.py`` runs a cloud's builder: it reads the
cloud's source over https (kept in ``<cache>/price-build`` so a rerun reads
the network once), reduces it to the rates the pricers read, and writes
``assets/prices/<cloud>.json`` (:mod:`infragram.pricing.tables`). Nothing
here runs at export time.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ...iso3d.cache import cache_root
from ..fetch import fetch_url
from ..tables import SCHEMA, Table, tables_dir

__all__ = ["download", "download_json", "write_table"]


def _cache() -> Path:
    folder = cache_root() / "price-build"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def download(url: str, *, fresh: bool = False) -> bytes:
    """The body at *url* (https only), kept in the build cache."""
    path = _cache() / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:40] + ".bin")
    if path.is_file() and not fresh:
        return path.read_bytes()
    body = fetch_url(url)
    partial = path.with_name(f"{path.name}.{os.getpid()}.part")
    partial.write_bytes(body)
    os.replace(partial, path)
    return body


def download_json(url: str, *, fresh: bool = False) -> Any:
    return json.loads(download(url, fresh=fresh))


def _rounded(value: Any) -> Any:
    if isinstance(value, float):
        return float(f"{value:.10g}")
    if isinstance(value, dict):
        return {key: _rounded(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


def write_table(
    cloud: str,
    services: dict[str, dict[str, Any]],
    *,
    read: str,
    currency: str = "USD",
    folder: Path | None = None,
) -> Path:
    """Write *cloud*'s table: validated, keys sorted, one service a line."""
    table = {
        "schema": SCHEMA,
        "cloud": cloud,
        "currency": currency,
        "read": read,
        "services": _rounded(services),
    }
    Table.model_validate(table)
    folder = folder or tables_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{cloud}.json"
    head = {key: value for key, value in table.items() if key != "services"}
    lines = [json.dumps(head, sort_keys=True)[:-1] + ', "services": {']
    names = sorted(table["services"])
    for index, name in enumerate(names):
        comma = "," if index < len(names) - 1 else ""
        body = json.dumps(table["services"][name], sort_keys=True, separators=(",", ":"))
        lines.append(f"{json.dumps(name)}:{body}{comma}")
    lines.append("}}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path
