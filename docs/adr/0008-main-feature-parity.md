# 0008: Share the full feature set with the Azure edition

Status: accepted, 2026-10-15.

The Azure edition kept useful subscription discovery and subnet annotations
while its editor, document model and exporter diverged from the full product.
Keeping two diverging editors cost more than sharing one.

Adopt the main editor, rendering and export code, including traffic flows,
touch editing, costs, optional offline 3D recipes, editable SVG/PNG documents,
draw.io and Terraform exports, diagram imports, review tools and MCP. Keep
Azure, Kubernetes and Databricks as the installed vendor libraries. Terraform
and live cloud discovery advertise only supported libraries.

Preserve Azure's multiple-subscription importer, saved snapshots, network and
resource-group views, public subnet frames, NAT edge badges and NSG corner
badges. Retain the existing Python entry points and explicit grid widths.
Fix NIC relationships when an NSG also belongs to a subnet.

Documents save as schema 3. Versions 1 and 2 migrate on load; legacy badge
sides and offsets remain supported. Files saved here use the main document
model, with additional Azure badge compatibility. An older Azure release
cannot open schema 3 without an upgrade.

Exports use temporary staging files, then move completed artifacts into place.
An unchanged generated artifact can be regenerated; edited artifacts remain
protected unless replacement is requested. Default `write_looks="both"` retains
the Azure edition's two-look output default; `write_looks="document"` selects
only the document's own look. Modern image exports embed their source and
only needed font faces, while the legacy standalone-SVG helper retains its
previous self-contained font contract.

These changes intentionally update the four templates' rendered appearance.
Accept new picture hashes only after all eight picture checks pass and the
rendered output has been inspected. Test packaged installs independently of
the checkout and exercise desktop, touch, downloads and badge round trips in
Chromium. Cost estimates and Terraform skeletons retain their documented
assumptions; no deployment is added.
