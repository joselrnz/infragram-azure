"""What an importer run would change in a catalog it rewrites, checked first.

The importers rebuild a vendor pack's ``catalog.json`` from an upstream
release. The catalogs they write have since been reviewed and extended by
hand: icons removed because they were fragments of a drawing, and whole sets
(the 3D on-premises items) added by other tools. A rerun that rebuilt from
upstream alone would drop the one and bring back the other, silently. So an
importer works out the ids it is about to write, before it writes anything,
and this says what that would lose or add; the importer refuses unless told
``--force``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path

__all__ = ["catalog_ids", "refusal"]


def catalog_ids(catalog: Path, owned: Callable[[str], bool] | None = None) -> set[str]:
    """The ids of the icons a catalog lists -- only those ``owned`` says this
    importer manages, when it shares the catalog with another tool."""
    if not catalog.is_file():
        return set()
    icons = json.loads(catalog.read_text(encoding="utf-8")).get("icons", [])
    ids = {str(icon["id"]) for icon in icons}
    return {icon for icon in ids if owned is None or owned(icon)}


def refusal(
    catalog: Path,
    planned: Iterable[str],
    *,
    owned: Callable[[str], bool] | None = None,
    force: bool = False,
) -> str | None:
    """Why writing ``planned`` over ``catalog`` is refused, or None when the run
    changes no id this importer manages (or ``force`` accepts that it does)."""
    before = catalog_ids(catalog, owned)
    if not before or force:
        return None
    after = set(planned)
    dropped, added = sorted(before - after), sorted(after - before)
    if not dropped and not added:
        return None

    def some(ids: list[str]) -> str:
        return ", ".join(ids[:6]) + (f" and {len(ids) - 6} more" if len(ids) > 6 else "")

    parts = []
    if dropped:
        parts.append(f"drop {len(dropped)} icons the catalog lists ({some(dropped)})")
    if added:
        parts.append(f"add {len(added)} it does not ({some(added)})")
    return (
        f"{catalog.parent.name}: this run would {' and '.join(parts)}. The catalog has been "
        "reviewed since it was imported: removed icons were removed on purpose and added "
        "ones belong to other tools. Nothing was written; pass --force to replace it anyway."
    )
