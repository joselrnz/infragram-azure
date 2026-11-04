---
name: compose
description: Build an infrastructure diagram from a Python diagram file (frames as with-blocks, automatic layout) and export it to HTML, SVG and PNG, and on request its Azure Terraform skeleton. Run when the user invokes it with a diagram file or asks for one to be written and drawn.
argument-hint: <diagram.py> [--formats html,svg,png] [--output-dir <dir>] [--display card|icon|both] [--prices|--no-prices] [--force]
disable-model-invocation: true
allowed-tools: Read Write Glob Bash(python:*) Bash(python3:*)
---

# Compose a diagram file

Turn the Python diagram file named first in the arguments (`$ARGUMENTS`) into
an infrastructure diagram. This command belongs to the Infragram Azure
plugin: the `infragram-azure` skill sits beside this skill's folder, and
`<plugin>` below is the folder holding both: `${CLAUDE_PLUGIN_ROOT}` in
Claude Code, and in Codex or Pi the folder two above this skill's own.

Read `<plugin>/skills/infragram-azure/references/compose.md` first: it shows
the form (`with Diagram(...)`, frames as `with` blocks, nodes written inside
them, `a >> Edge("label") >> b` for wires), lists the node-class packages and
the frame classes per library, and says what the diagram infers (components,
providers, kind, placement).

If the user described an estate but has no file yet, write one in their
directory in that form, naming services through `infragram.nodes.<library>`
classes (`azure`, `kubernetes`, `databricks`, and the shared `infragram`) and
nesting them in `infragram.nodes.frames.<library>` frames. Never place
coordinates by hand; the renderer lays the tree out.

Run it from the user's directory, so the file and output paths mean what they
say there:

```bash
python "<plugin>/skills/infragram-azure/scripts/infragram.py" compose <the arguments> --verify
```

Use `python3` where `python` is not Python 3. It writes `html,svg,png` into
`./dist` unless `--formats` or `--output-dir` say otherwise; without
Playwright and Chromium it writes the HTML and SVG and says why the PNG is
missing. `--display both` writes the card look under the plain names and the
icon look as `<slug>-icons.*`. `terraform` in `--formats` also writes the
diagram's Azure Terraform skeleton, `<slug>-terraform/`
(`references/terraform.md`); report its folder and the variables its note says
are left to fill. Every export prices the Azure components from the shipped
price tables (no network): report the `PRICED` total, what was assumed and
what is not priced, and point the user to the page's Cost tab for the detail.
`--prices` reads live prices where it can; `--no-prices` leaves prices out.
Exporting again replaces what the last export wrote; `--force` is needed only
for a file the command refuses (written elsewhere, or edited since), and only
when the user means to lose that edit. Report the `PROJECT` line (slug, kind,
libraries, element count), every produced path and byte size, and the
verification verdict.
