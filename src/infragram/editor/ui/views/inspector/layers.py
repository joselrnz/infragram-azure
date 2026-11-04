"""Layers panel: the frame hierarchy and the provider layers.

Styles: inspector.css. Both lists are written by the runtime, so what is here
is the headings and the two places they land.
"""

from __future__ import annotations


def panel() -> str:
    return """            <section class="inspector-section" data-inspector-panel="layers" role="tabpanel" hidden>
              <h2>Layers</h2>
              <h3>Frame hierarchy</h3>
              <div class="md-list frame-tree" data-frame-tree></div>
              <h3>Provider layers</h3>
              <p>Visibility never deletes objects. Locked layers remain exportable but cannot be moved.</p>
              <div class="md-list layer-list" data-layer-list></div>
            </section>"""


__all__ = ["panel"]
