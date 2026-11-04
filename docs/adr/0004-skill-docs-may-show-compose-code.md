# ADR 0004 - Skill documents may show compose code that imports the shipped package

**Status:** accepted (0.1.0)

## Context

`tests/skill/test_skill_is_self_contained.py` keeps the shipped skill free of
references to the development tree: SKILL.md and every reference document
may not mention `src/infragram`, `scripts/verify/`, `scripts/build/`, or the
string `from infragram`. The rule exists so that an agent reading the skill is
never sent to a path that only exists in this repository.

The rule predates composing as code. The skill's own workflow
tells the agent to build a diagram in Python -- `from infragram import
compose`, node classes from `infragram.nodes` -- and to run it with
`PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src"`. The package ships inside the plugin;
an import of it is the product working as designed, not a pointer at the
development tree. `references/compose.md` carries `from infragram` in its
code samples.

## Decision

The rule distinguishes code from prose. Inside a fenced code block or an
inline code span, `from infragram` and `import infragram` are allowed: that
is the compose workflow, and the package is shipped. Outside code, they stay
forbidden, as do `src/infragram`, `scripts/verify/` and `scripts/build/`
everywhere, because those are paths into this repository.

## Consequences

- `compose.md` and `patterns.md` pass as written, and the samples in them
  stay runnable from an installed plugin.
- An agent-facing document still cannot tell the reader to open a file under
  `src/` or run a development gate.
- The check is unchanged in every other respect and still runs from the
  script path CI uses; the workflow in `.forgejo/workflows/ci.yml` runs it on
  every push, so a regression of this kind is seen the same day.
