"""The page: the document shell every other view is placed into.

One file is the whole product here -- the markup, the stylesheet, the runtime
and every icon of every installed library travel together, because an export
has to open from a file:// URL on a machine that has never heard of this
repository. That is why the scripts are inlined rather than linked, and why
the library catalog rides along compressed.
"""

from __future__ import annotations

from html import escape

from ..branding import mascot_uri


def page(
    *,
    title: str,
    font_faces: str,
    stylesheet: str,
    sidebar: str,
    header: str,
    canvas: str,
    inspector: str,
    drawer: str,
    data_scripts: str,
    iso3d_bundle: str,
    runtime: str,
) -> str:
    """The whole editor document, from its parts."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark light">
  <title>{escape(title)} · Infragram Azure</title>
  <link rel="icon" type="image/png" href="{mascot_uri(32)}">
  {font_faces}
  <style>
{stylesheet}
  </style>
</head>
<body data-workspace-theme="light">
  <div class="workspace">
{sidebar}
    <main class="editor-main">
{header}
      <div class="editor-workbench">
{canvas}
        <div class="dock-divider dock-divider--right" data-dock-divider="right" role="separator" aria-orientation="vertical" aria-label="Resize the inventory" tabindex="0" hidden></div>
        <aside class="resource-dock" data-resource-dock aria-label="Inventory" hidden></aside>
{inspector}
      </div>
{drawer}
    </main>
  </div>
{data_scripts}
  <script data-infragram-iso3d>
{iso3d_bundle}
  </script>
  <script data-infragram-editor>
{runtime}
  </script>
</body>
</html>
"""


__all__ = ["page"]
