"""Sidebar view: the brand, search, the library selector and the category list.

Styles: sidebar.css.

This is the one region of the chrome that is different in every export. The
full edition ships nineteen provider libraries, so nothing here may name one
of them: the brand mark, the monogram it falls back to and the architecture
label all come from the catalog the project loaded, and a workspace spanning
more than one infrastructure library is branded as multicloud rather than as
whichever library happened to be first.
"""

from __future__ import annotations

from html import escape

from ....catalog import load_default_category_registry, load_default_provider_registry
from ....projects import CloudProject
from ...artwork import _category_icon
from ...sidebar import SidebarCatalog
from ..icons import icon


def connected_cloud_mark() -> str:
    return """<svg class="provider-mark multicloud-mark" data-multicloud-mark="true"
               viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <path d="M11 26h17a7 7 0 0 0 .7-14A10 10 0 0 0 9.8 14.7 6 6 0 0 0 11 26Z"
            stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
      <path d="M8 31h24M14 26v5M26 26v5" stroke="var(--accent)" stroke-width="2"/>
      <circle cx="8" cy="31" r="2.5" fill="var(--accent)"/>
      <circle cx="20" cy="31" r="2.5" fill="var(--text-primary)"/>
      <circle cx="32" cy="31" r="2.5" fill="var(--accent)"/>
    </svg>"""


def provider_summary(selected: tuple[str, ...], available: int | None = None) -> str:
    registry = load_default_provider_registry()
    if len(selected) == (available if available is not None else len(registry.providers)):
        return f"All {len(selected)}"
    names = [registry[provider].chip for provider in selected]
    if len(names) <= 3:
        return " + ".join(names)
    return f"{names[0]} + {names[1]} +{len(names) - 2}"


def provider_selector(payload: dict[str, object], selected: tuple[str, ...]) -> str:
    providers = payload["providers"]
    assert isinstance(providers, list)

    def option(provider: dict[str, object]) -> str:
        provider_id = str(provider["id"])
        checked = " checked" if provider_id in selected else ""
        mark = (
            f'<img src="{provider["markUri"]}" alt="" width="24" height="24">'
            if provider.get("markUri")
            else f'<span class="provider-option-monogram">{escape(str(provider["shortName"])[:2])}</span>'
        )
        return f"""          <label class="md-list-item md-list-item--dense provider-option" data-provider-row="{provider_id}">
            <input type="checkbox" class="md-checkbox" data-provider-option="{provider_id}"{checked}>
            {mark}
            <span class="md-list-item__headline provider-option-name">{escape(str(provider["displayName"]))}</span>
            <span class="md-list-item__trailing coverage-badge" data-coverage="{provider["coverage"]}">{escape(str(provider["coverage"]).title())}</span>
          </label>"""

    clouds = "\n".join(option(provider) for provider in providers if provider["kind"] == "cloud")
    platforms = "\n".join(
        option(provider) for provider in providers if provider["kind"] == "platform"
    )
    local_infrastructure = "\n".join(
        option(provider) for provider in providers if provider["kind"] == "on-prem"
    )
    # Which libraries get a one-click filter is the catalog's to say, not
    # this view's: it used to be a tuple of three ids written in here, in a
    # product that ships nineteen.
    quick = "\n".join(
        f"""        <button type="button" class="md-chip provider-quick-filter" data-provider-quick-filter="{provider["id"]}"
                aria-pressed="{"true" if provider["id"] in selected else "false"}">{escape(str(provider["chipName"]))}</button>"""
        for provider in providers
        if provider.get("quickFilter")
    )

    def group(label: str, options: str) -> str:
        # a heading only over something to choose
        return (
            f'          <p class="md-menu__header provider-group-label">{label}</p>\n{options}'
            if options
            else ""
        )

    summary = provider_summary(selected, len(providers))
    # one library is nothing to choose between: the picker stays out of sight
    alone = " hidden" if len(providers) <= 1 else ""
    return f"""      <section class="provider-selector" aria-label="Provider libraries"{alone}>
        <button type="button" class="md-button md-button--outlined md-button--block provider-menu-trigger" data-provider-menu-trigger
                aria-expanded="false" aria-controls="provider-library-menu">
          <span>Libraries · <strong data-provider-summary>{escape(summary)}</strong></span>
          {icon("expand", extra_class="md-expand-icon")}
        </button>
        <div class="md-chip-set provider-quick-filters" aria-label="Quick provider filters">
{quick}
        </div>
        <div id="provider-library-menu" class="md-menu provider-menu" data-provider-menu role="dialog"
             aria-label="Choose provider libraries" hidden>
          <div class="provider-menu-actions">
            <button type="button" class="md-button md-button--text" data-provider-select-all>Select all</button>
            <button type="button" class="md-button md-button--text" data-provider-clear>Clear</button>
          </div>
{group("Cloud providers", clouds)}
{group("Platforms", platforms)}
{group("Local infrastructure", local_infrastructure)}
          <button type="button" class="md-button md-button--filled md-button--block provider-apply" data-provider-apply>Apply</button>
        </div>
      </section>"""


def uses_multicloud_brand(project: CloudProject) -> bool:
    """Brand cloud-plus-platform workspaces with their primary cloud provider."""

    if project.kind == "multicloud":
        return True
    registry = load_default_provider_registry()
    infrastructure = tuple(
        provider_id
        for provider_id in project.provider_ids
        if registry[provider_id].kind != "platform"
    )
    return len(infrastructure) > 1


def shows_provider_mark(project: CloudProject) -> bool:
    """Whether the picture carries its provider's lockup in the corner.

    Not on a multicloud picture, which is branded as such, and not on one
    drawn from shared parts with nothing from a vendor library: a drawing of
    shared parts and core frames only -- a homelab, another cloud's estate --
    falls back to the first provider for its theme, and its lockup there
    would credit a vendor the picture does not show. A drawing of plain
    cards with no components at all keeps the provider it names.
    """
    if uses_multicloud_brand(project):
        return False
    vendors = set(project.provider_ids)
    shared = False
    for element in project.topology.walk():
        if str(element.attributes.get("editor_frame_group") or "") in vendors:
            return True
        if element.component is not None:
            if element.component.provider in vendors:
                return True
            shared = True
    return not shared


def sidebar(
    project: CloudProject,
    catalog: SidebarCatalog,
    payload: dict[str, object],
) -> str:
    multicloud = uses_multicloud_brand(project)
    if multicloud:
        mark = connected_cloud_mark()
        provider_label = "Multicloud Diagrams"
    else:
        mark = (
            f'<img class="provider-mark" src="{catalog.provider_mark_uri}" alt="" width="36" height="36"'
            + (' data-mark-look="light">' if catalog.provider_mark_dark_uri else ">")
            + (
                f'<img class="provider-mark" src="{catalog.provider_mark_dark_uri}" alt="" width="36" '
                'height="36" data-mark-look="dark">'
                if catalog.provider_mark_dark_uri
                else ""
            )
            if catalog.provider_mark_uri
            else f'<span class="provider-monogram">{escape(catalog.provider_name[:1])}</span>'
        )
        provider_label = f"{catalog.provider_name} Diagrams"
    selected = tuple(provider.id for provider in project.providers if provider.enabled)
    categories = []
    category_registry = load_default_category_registry()
    for category in category_registry.categories:
        categories.append(
            f"""        <details class="category" data-category-id="{category.id}">
          <summary class="md-nav-item">
            {_category_icon(category.id)}
            <span class="category-label">{escape(category.label)}</span>
            <span class="category-count" data-category-count="{category.id}">0</span>
            {icon("expand", extra_class="md-expand-icon chevron-icon")}
          </summary>
          <div class="component-list" data-component-list="{category.id}"></div>
        </details>"""
        )
    return f"""    <aside id="provider-sidebar" class="provider-sidebar" data-testid="provider-sidebar"
           data-provider-label="{escape(provider_label, quote=True)}" data-library-render-mode="lazy">
      <header class="provider-header">
        <button type="button" class="md-nav-item provider-brand" data-sidebar-logo-trigger
                aria-controls="provider-sidebar" aria-expanded="true"
                aria-label="Collapse {escape(provider_label, quote=True)} sidebar">
          <span class="provider-brand-mark" aria-hidden="true">{mark}</span>
          <span class="provider-name"><strong>{escape(provider_label)}</strong>
            <small class="provider-context">Infragram Azure</small>
          </span>
          <svg class="sidebar-state-icon" data-sidebar-control-icon viewBox="0 0 16 16"
               fill="none" stroke="currentColor" stroke-width="1.35" aria-hidden="true">
            <rect x="1.75" y="2.25" width="12.5" height="11.5" rx="2"/>
            <path d="M5.75 2.25v11.5"/>
          </svg>
        </button>
      </header>
      <label class="md-search search-box">
        <svg class="md-icon search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M16 16l5 5"/></svg>
        <span class="sr-only">Search components</span>
        <input type="search" placeholder="Search components" autocomplete="off" data-sidebar-search>
      </label>
{provider_selector(payload, selected)}
      <nav class="category-list" aria-label="Infrastructure components">
{chr(10).join(categories)}
        <p class="empty-category" data-search-empty role="status" hidden></p>
      </nav>
    </aside>"""


__all__ = [
    "connected_cloud_mark",
    "provider_selector",
    "provider_summary",
    "shows_provider_mark",
    "sidebar",
    "uses_multicloud_brand",
]
