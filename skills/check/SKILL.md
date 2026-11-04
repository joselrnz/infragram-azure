---
name: check
description: Check Infragram documents and exported pages - .infragram.json, HTML, SVG, PNG - for structure, real components and, for an SVG, the picture itself; optionally render a diagram several times and check both looks. Run when the user invokes it with files to check.
argument-hint: <file>... [--render]
disable-model-invocation: true
allowed-tools: Read Glob Bash(python:*) Bash(python3:*)
---

# Check diagrams

Check the files named in the arguments (`$ARGUMENTS`): `.infragram.json`
documents, exported pages (`.html`, `.svg`, `.png`) and Python diagram files,
which are read and never run (what they draw is `compose --verify`'s to
check). This command belongs to the Infragram Azure plugin: the
`infragram-azure` skill sits beside this skill's folder, and `<plugin>` below
is the folder holding both: `${CLAUDE_PLUGIN_ROOT}` in Claude Code, and in
Codex or Pi the folder two above this skill's own. Run from the user's
directory:

```bash
python "<plugin>/skills/infragram-azure/scripts/infragram.py" check <files>
```

When the user passes `--render`, or asks whether the picture itself is right,
also render each document or page three separate times, prove the passes
identical, and check the picture in both looks:

```bash
python "<plugin>/skills/infragram-azure/scripts/infragram.py" verify:render <files> --passes 3 --display both
```

Use `python3` where `python` is not Python 3. Add `--json` when a program
reads the result: one JSON document with every file's kind, verdict, problems
and counts, and the same exit status. The checker reads the files; it
changes nothing. Report the verdict for each file and every problem it names,
and, when a problem is the diagram's, what in the document or diagram file
causes it (`<plugin>/skills/infragram-azure/SKILL.md` has the rules).
Do not fix anything unless the user asks.
