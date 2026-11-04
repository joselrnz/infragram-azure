"""Where a component is read about: the links a card's popup shows.

``assets/catalog/links.json`` holds them. A component it lists (``aws:ec2``)
has its own pages -- the product, its pricing, its documentation, the
pricing calculator. Every other component of a vendor library gets a search
of that vendor's own site for the component's name, so every card on AWS,
Azure, Google Cloud and the other clouds and platforms links somewhere from
the first day, and a curated entry replaces the search one component at a
time. Local & On-Premises and the shared ``infragram`` library name no
vendor and have no search.

The page resolves the links itself, from the table it carries
(:func:`runtime_json`), so a card added in the editor has them too and a
saved document holds none.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import lru_cache
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..paths import skill_assets

__all__ = ["ComponentLink", "LinkTable", "LibrarySearch", "links_for", "load_links", "runtime_json"]


def _https(url: str) -> str:
    if not url.startswith("https://"):
        raise ValueError(f"a link must be https: {url!r}")
    return url


class ComponentLink(BaseModel):
    """One page about a component."""

    model_config = ConfigDict(frozen=True)

    label: str
    url: str

    @field_validator("url")
    @classmethod
    def _secure(cls, url: str) -> str:
        return _https(url)


class LibrarySearch(BaseModel):
    """A vendor's site, and its search for a component's name (``{query}``)."""

    model_config = ConfigDict(frozen=True)

    site: str
    search: str

    @field_validator("search")
    @classmethod
    def _query(cls, search: str) -> str:
        if "{query}" not in search:
            raise ValueError(f"a search must say where the query goes ({{query}}): {search!r}")
        return _https(search)


class LinkTable(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(alias="schema")
    about: str = ""
    libraries: dict[str, LibrarySearch]
    components: dict[str, list[ComponentLink]]


@lru_cache(maxsize=1)
def load_links() -> LinkTable:
    return LinkTable.model_validate_json(
        (skill_assets() / "catalog" / "links.json").read_text(encoding="utf-8")
    )


def links_for(component: str, name: str) -> list[ComponentLink]:
    """The links for a component (``aws:ec2``) called *name*: its own pages,
    else a search of its vendor's site for the name, else none."""
    table = load_links()
    if component in table.components:
        return list(table.components[component])
    library = table.libraries.get(component.partition(":")[0])
    if library is None or not name.strip():
        return []
    url = library.search.replace("{query}", quote(name.strip(), safe=""))
    return [ComponentLink(label=f"Search {library.site}", url=url)]


def runtime_json(providers: Iterable[str] | None = None) -> str:
    """The table as the page carries it (made script-safe by the page), for
    the runtime to resolve links from: only the libraries the page embeds,
    when it says which, since no card of another can be added in it."""
    table = load_links()
    wanted = None if providers is None else set(providers)
    return json.dumps(
        {
            "libraries": {
                key: library.model_dump()
                for key, library in table.libraries.items()
                if wanted is None or key in wanted
            },
            "components": {
                key: [link.model_dump() for link in links]
                for key, links in table.components.items()
                if wanted is None or key.partition(":")[0] in wanted
            },
        },
        separators=(",", ":"),
    )
