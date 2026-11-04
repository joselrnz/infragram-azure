"""Cost panel: what the diagram costs a month, approximately, in detail.

Styles: inspector.css. Everything under the heading is written by the
runtime (34-costs) from the prices the export wrote into the document: the
total, its fixed and usage parts, each frame's subtotal, every priced item
with the lines it adds up from, what was assumed, and what is free or not
priced and why.
"""

from __future__ import annotations


def panel() -> str:
    return """            <section class="inspector-section cost-panel" data-inspector-panel="cost" role="tabpanel" hidden>
              <h2>Cost</h2>
              <div class="cost-summary" data-cost-summary></div>
              <h3 data-cost-heading="frames">By frame</h3>
              <div class="cost-frames" data-cost-frames></div>
              <h3 data-cost-heading="items">Items, most first</h3>
              <div class="cost-items" data-cost-items></div>
              <h3 data-cost-heading="assumed">Assumed</h3>
              <ul class="cost-assumed" data-cost-assumed></ul>
              <h3 data-cost-heading="unpriced">Not priced</h3>
              <ul class="cost-unpriced" data-cost-unpriced></ul>
              <p class="cost-note" data-cost-note></p>
            </section>"""


__all__ = ["panel"]
