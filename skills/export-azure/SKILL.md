---
name: export-azure
description: Read live Azure subscriptions through the az CLI, or redraw a saved snapshot offline, and export them as a network or resource-group diagram. Run when the user invokes it, optionally with subscriptions, a view or a snapshot.
argument-hint: [--subscription <name-or-id>]... [--management-group <name>]... [--view network|groups|both] [--resource-group <pattern>]... [--snapshot-out estate.json | --from-snapshot estate.json] [--formats template,html,svg,png] [--force]
disable-model-invocation: true
allowed-tools: Read Glob Bash(python:*) Bash(python3:*)
---

# Draw Azure subscriptions

Draw what is deployed in Azure. This command belongs to the Infragram Azure
plugin: the `infragram-azure` skill sits beside this skill's folder, and
`<plugin>` below is the folder holding both: `${CLAUDE_PLUGIN_ROOT}` in
Claude Code, and in Codex or Pi the folder two above this skill's own.

Read `<plugin>/skills/infragram-azure/references/azure-import.md` first: it
says what each view places where, what is left out by default, and how
peerings into other subscriptions are drawn.

A saved snapshot (`--from-snapshot`) needs no sign-in. A live read uses the
Azure CLI's own session and never asks for a secret. Check it first:

```bash
python "<plugin>/skills/infragram-azure/scripts/infragram.py" export:azure --list-subscriptions
```

If that fails with a sign-in error, ask the user to run `az login` (or
`az login --tenant <id>`) themselves; never handle their credentials. If the
user did not name a subscription, draw the current one (marked `*`), and when
a VNet peers into a subscription that was not read, say so and offer to add
it with another `--subscription`. Run it from the user's directory:

```bash
python "<plugin>/skills/infragram-azure/scripts/infragram.py" export:azure <the arguments> --verify
```

Use `python3` where `python` is not Python 3. Defaults: the network view,
icons with captions, and `template,html,svg,png` into `./dist`. `--snapshot-out estate.json`
keeps what was read so the same drawing can be made again offline. Never add
`--force` unless the user explicitly intends to replace the named files.
Report each `PROJECT` block (the summary lines say what was placed, left out
and drawn with the generic icon), the `PRICED` total with what was assumed,
every produced path and byte size, and the verification verdict.
