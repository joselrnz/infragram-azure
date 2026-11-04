"""The chrome's glyphs: a 24-unit grid, a 1.5 stroke, currentColor."""

from __future__ import annotations

ICON_PATHS = {
    # the components drawer on a phone: tiles, and one to add
    "library": '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><path d="M16.75 13.5v6.5M13.5 16.75H20"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "redo": '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    "delete": '<path d="M4 7h16M10 11v6M14 11v6"/><path d="m6 7 1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/><path d="M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7"/>',
    "zoom-out": '<path d="M5 12h14"/>',
    "zoom-in": '<path d="M12 5v14M5 12h14"/>',
    "fit": '<path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/><rect x="8.5" y="8.5" width="7" height="7" rx="1"/>',
    "grid": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9.5h16M4 14.5h16M9.5 4v16M14.5 4v16"/>',
    # Three boxes snapping back onto one baseline: the layout doing the placing.
    "tidy": '<rect x="3.5" y="5" width="5" height="5" rx="1"/><rect x="11" y="5" width="9.5" height="5" rx="1"/><rect x="3.5" y="14" width="9.5" height="5" rx="1"/><path d="M16 14v5M18.5 14v5"/>',
    "download": '<path d="M12 3v12m-4-4 4 4 4-4"/><path d="M5 16v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 16 5-5 4 4 4-5 5 6"/>',
    "vector": '<rect x="3" y="3" width="4" height="4" rx="1"/><rect x="17" y="3" width="4" height="4" rx="1"/><path d="M7 5h10M5 7v10m14-10v10M5 19h3m8 0h3"/><rect x="8" y="15" width="8" height="6" rx="1"/>',
    "diagram": '<rect x="8" y="3" width="8" height="5" rx="1"/><path d="M12 8v5M5 16v-3h14v3"/><rect x="2" y="16" width="6" height="5" rx="1"/><rect x="16" y="16" width="6" height="5" rx="1"/>',
    "file-code": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6m-10 3-3 3 3 3m4-6 3 3-3 3"/>',
    "browser": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01m-1 6-2 2 2 2m6-4 2 2-2 2"/>',
    "expand": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "align-left": '<path d="M4 4v16"/><rect x="8" y="6" width="12" height="4" rx="1"/><rect x="8" y="14" width="7" height="4" rx="1"/>',
    "align-center": '<path d="M12 3v3M12 10v4M12 18v3"/><rect x="5" y="6" width="14" height="4" rx="1"/><rect x="8" y="14" width="8" height="4" rx="1"/>',
    "align-right": '<path d="M20 4v16"/><rect x="4" y="6" width="12" height="4" rx="1"/><rect x="9" y="14" width="7" height="4" rx="1"/>',
    "align-top": '<path d="M4 4h16"/><rect x="6" y="8" width="4" height="12" rx="1"/><rect x="14" y="8" width="4" height="7" rx="1"/>',
    "align-middle": '<path d="M3 12h3M10 12h4M18 12h3"/><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="8" width="4" height="8" rx="1"/>',
    "align-bottom": '<path d="M4 20h16"/><rect x="6" y="4" width="4" height="12" rx="1"/><rect x="14" y="9" width="4" height="7" rx="1"/>',
    "distribute-horizontal": '<path d="M4 4v16M20 4v16"/><rect x="9" y="7" width="6" height="10" rx="1"/>',
    "distribute-vertical": '<path d="M4 4h16M4 20h16"/><rect x="7" y="9" width="10" height="6" rx="1"/>',
    "rotate": '<path d="M20 11a8 8 0 1 1-2.34-5.66"/><path d="M20 4v5h-5"/>',
    "flip-horizontal": '<path d="M12 3v18"/><path d="M8 7 3 17h5z"/><path d="m16 7 5 10h-5z"/>',
    "flip-vertical": '<path d="M3 12h18"/><path d="M7 8 17 3v5z"/><path d="m7 16 10 5v-5z"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.2 2.4c-.5.2-.7.6-.7 1.1v.5"/><path d="M12 17h.01"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 5H6a1 1 0 0 0-1 1v9"/><path d="M12.5 14.5h4M14.5 12.5v4"/>',
    "to-front": '<path d="M8 16H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v3"/><rect x="8" y="8" width="12" height="12" rx="1.5" fill="currentColor" fill-opacity=".24"/>',
    "group": '<rect x="3" y="3" width="18" height="18" rx="2" stroke-dasharray="3 2.5"/><rect x="7" y="7" width="5" height="5" rx="1"/><rect x="12" y="12" width="5" height="5" rx="1"/>',
    "detach": '<path d="M14 4h6v6"/><path d="m20 4-8 8"/><path d="M10 5H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-4"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "palette": '<path d="M12 3a9 9 0 0 0 0 18c1 0 1.7-.8 1.7-1.7 0-.4-.2-.8-.4-1.1-.3-.3-.4-.7-.4-1.1 0-.9.8-1.7 1.7-1.7H17a4 4 0 0 0 4-4c0-4.6-4-8.4-9-8.4z"/>'
    '<circle cx="7.5" cy="11.5" r="1" fill="currentColor"/><circle cx="10" cy="7.5" r="1" fill="currentColor"/>'
    '<circle cx="14.5" cy="7.5" r="1" fill="currentColor"/><circle cx="17" cy="11.5" r="1" fill="currentColor"/>',
    "show-icons": '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
    "show-cards": '<rect x="3" y="5" width="18" height="6" rx="1.5"/><rect x="3" y="13" width="18" height="6" rx="1.5"/><path d="M6 8h3M6 16h3"/>',
    "swap": '<path d="M4 8h14l-3.5-3.5M20 16H6l3.5 3.5"/>',
    "route-reset": '<path d="M5 19V10a4 4 0 0 1 4-4h9"/><path d="m15 3 3 3-3 3"/><circle cx="5" cy="19" r="1.5"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    # The right-click menu: what each entry does to the item or the view.
    "inspect": '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>',
    "center": '<circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="1.5"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>',
    "dependents": '<path d="m12 4 8 4-8 4-8-4z"/><path d="m4 12 8 4 8-4"/><path d="m4 16 8 4 8-4"/>',
    "magnify-plus": '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5M8.5 11h5M11 8.5v5"/>',
    "magnify-minus": '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5M8.5 11h5"/>',
    "actual-size": '<path d="M6 9.5 8 8v8M16 9.5 18 8v8"/><circle cx="12" cy="10.5" r=".75" fill="currentColor" stroke="none"/><circle cx="12" cy="14.5" r=".75" fill="currentColor" stroke="none"/>',
    "scroll-pan": '<rect x="7" y="3.5" width="10" height="17" rx="5"/><path d="M12 7.5v3"/>',
    "paste": '<rect x="5" y="5" width="14" height="16" rx="2"/><path d="M9 5V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1"/><path d="M9 12h6M9 16h4"/>',
    "more": '<circle cx="6" cy="12" r="1.25" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.25" fill="currentColor" stroke="none"/><circle cx="18" cy="12" r="1.25" fill="currentColor" stroke="none"/>',
    "globe": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.5 5.4 3.5 8.5s-1.1 6.1-3.5 8.5c-2.4-2.4-3.5-5.4-3.5-8.5s1.1-6.1 3.5-8.5z"/>',
    "coin": '<circle cx="12" cy="12" r="8.5"/><path d="M14.5 9.5c-.4-.9-1.4-1.5-2.5-1.5-1.5 0-2.5.8-2.5 2s1 1.7 2.5 2 2.5.8 2.5 2-1 2-2.5 2c-1.1 0-2.1-.6-2.5-1.5M12 6.5V8M12 16v1.5"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "shield": '<path d="M12 3.5 5 6v5.5c0 4.2 3 7.6 7 9 4-1.4 7-4.8 7-9V6z"/><path d="M12 8.5v4M12 15.5v.01"/>',
    # the inventory docked beside the map, under it, or the map and table split
    "dock-right": '<rect x="3.5" y="5" width="17" height="14" rx="1.5"/><path d="M14 5v14"/><path d="M16.5 9h1.5M16.5 12h1.5M16.5 15h1.5"/>',
    "dock-bottom": '<rect x="3.5" y="5" width="17" height="14" rx="1.5"/><path d="M3.5 13h17"/><path d="M7 16h10"/>',
    # The inventory: a table of rows.
    "table": '<rect x="3.5" y="5" width="17" height="14" rx="1.5"/><path d="M3.5 9.5h17M3.5 14h17M9 9.5V19"/>',
    "edit": '<path d="M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17z"/><path d="m14 8 3 3"/>',
    "select": '<path d="m6 4 4.5 15 2.3-6.2L19 10.5z"/><path d="m13.5 13.5 5 5"/>',
    "text": '<path d="M5 6V4.5h14V6M12 4.5v15M9 19.5h6"/>',
    # Six dots: the handle a floating bar is dragged by.
    "grip": '<circle cx="9" cy="6" r="1.25" fill="currentColor" stroke="none"/><circle cx="15" cy="6" r="1.25" fill="currentColor" stroke="none"/>'
    '<circle cx="9" cy="12" r="1.25" fill="currentColor" stroke="none"/><circle cx="15" cy="12" r="1.25" fill="currentColor" stroke="none"/>'
    '<circle cx="9" cy="18" r="1.25" fill="currentColor" stroke="none"/><circle cx="15" cy="18" r="1.25" fill="currentColor" stroke="none"/>',
    # Terraform's mark, from Tabler Icons' brand-terraform (MIT), as the
    # primitive icon of the same name draws it (references/primitive-icons.md).
    "terraform": '<path d="M15 15.5l-11.476 -6.216a1 1 0 0 1 -.524 -.88v-4.054a1.35 1.35 0 0 1 2.03 -1.166l9.97 5.816v10.65a1.35 1.35 0 0 1 -2.03 1.166l-3.474 -2.027a1 1 0 0 1 -.496 -.863v-11.926"/>'
    '<path d="M15 15.5l5.504 -3.21a1 1 0 0 0 .496 -.864v-3.576a1.35 1.35 0 0 0 -2.03 -1.166l-3.97 2.316"/>',
}


def icon(name: str, *, extra_class: str = "") -> str:
    classes = f"md-icon {extra_class}".strip()
    return (
        f'<svg class="{classes}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true" focusable="false">{ICON_PATHS[name]}</svg>'
    )


__all__ = ["ICON_PATHS", "icon"]
