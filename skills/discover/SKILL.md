---
name: discover
description: Draw a live Azure subscription or a Kubernetes cluster, read-only through the az CLI or kubectl as the user is signed in, as an editable diagram file and a report, exported to HTML, SVG and PNG. Run when the user invokes it with azure or kubernetes.
argument-hint: <azure | kubernetes> [--subscription S] [--resource-group G] [--source resource-graph] [--context C] [--namespace N] [--include-system] [--output-dir <dir>] [--force]
disable-model-invocation: true
allowed-tools: Read Write Glob Bash(python:*) Bash(python3:*)
---

# Draw a live Azure subscription or cluster

Draw the estate named first in the arguments (`$ARGUMENTS`): `azure` for a
subscription, or `kubernetes` for a cluster. This command belongs to the
Infragram Azure plugin: the `infragram-azure` skill sits beside this skill's
folder, and `<plugin>` below is the folder holding both:
`${CLAUDE_PLUGIN_ROOT}` in Claude Code, and in Codex or Pi the folder two
above this skill's own.

Read `<plugin>/skills/infragram-azure/references/terraform.md` section 3
first: it says what is drawn, what is folded or left out, and why. The estate
is read through `az`, or `kubectl` for a cluster, as the user is already
signed in, with list and show (or get) calls only. Pass the rest of the
arguments on: `--subscription`, `--resource-group` (repeatable) and
`--source resource-graph` for Azure, `--context`, `--namespace` (repeatable)
and `--include-system` for Kubernetes. Run from the user's directory, for
example:

```bash
python "<plugin>/skills/infragram-azure/scripts/infragram.py" discover:azure --subscription Production --verify
python "<plugin>/skills/infragram-azure/scripts/infragram.py" discover:kubernetes --context production --verify
```

Use `python3` where `python` is not Python 3. If `az` or `kubectl` answers
with a sign-in error, ask the user to sign in themselves (`az login`,
`az login --tenant <id>`); never handle their credentials, and never sign
them in or out. Never run a cloud command that creates, changes or deletes
anything.

This draws one subscription as an editable diagram file to change and
compose again. For several subscriptions at once, the network or
resource-group views, or a saved snapshot to redraw offline, the user's
`export-azure` command is the one to use.

A second discovery replaces what the first wrote; never add `--force` for a
file it refuses (edited since) unless the user explicitly intends to lose
that edit. Report the `READ`, `SPEC` and `REPORT` lines, every produced path
and byte size, the `PRICED` total with what was assumed, the verification
verdict, and the notes about what could not be read. The diagram file is the
starting point: offer to regroup or recaption it, then compose it again.
