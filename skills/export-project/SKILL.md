---
name: export-project
description: Export an .infragram.json infrastructure project, or an exported SVG, PNG or page that carries one, to HTML, SVG and PNG, and on request its Azure Terraform skeleton. Run when the user invokes it with a document or picture.
argument-hint: <project.infragram.json> [--formats html,svg,png] [--output-dir <dir>] [--scale N] [--prices|--no-prices] [--force]
disable-model-invocation: true
allowed-tools: Read Glob Bash(python:*) Bash(python3:*)
---

# Export a document

Export the infrastructure project named first in the arguments (`$ARGUMENTS`).
This command belongs to the Infragram Azure plugin: the `infragram-azure`
skill sits beside this skill's folder, and `<plugin>` below is the folder
holding both: `${CLAUDE_PLUGIN_ROOT}` in Claude Code, and in Codex or Pi the
folder two above this skill's own.

Read `<plugin>/skills/infragram-azure/references/export.md` first and keep its
one-render and no-overwrite rules. Run it from the user's directory, so the
project and output paths mean what they say there:

```bash
python "<plugin>/skills/infragram-azure/scripts/infragram.py" export:project <the arguments> --verify
```

Use `python3` where `python` is not Python 3. It writes `html,svg,png` into
`./dist` unless `--formats` or `--output-dir` say otherwise; add `template` to
`--formats` for a separate `.infragram.json` beside the page. Without
Playwright and Chromium it writes the HTML and SVG and says why the PNG is
missing. `terraform` in `--formats` also writes the diagram's Azure Terraform
skeleton, `<slug>-terraform/` (`references/terraform.md`); report its folder
and the variables its note says are left to fill. Every export prices the
Azure components from the shipped price tables (no network): report the
`PRICED` total, what was assumed and what is not priced, and point the user
to the page's Cost tab for the detail. `--prices` reads live prices where it
can; `--no-prices` leaves prices out. Exporting again replaces what the last
export wrote; `--force` is needed only for a file the command refuses
(written elsewhere, or edited since), and only when the user means to lose
that edit. Report every produced path and byte size, and the verification
verdict.
