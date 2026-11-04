"""The chrome's type: Inter (the drawing's face too), on the type scale, at each role's tracking.

Material 3 sets text by role -- title, body, label in three sizes -- and each
role is a face, a size, a line height, a weight and a tracking together
(material-web ``tokens/versions/latest/sass/_md-sys-typescale.scss``). The
``font`` shorthand carries all but the tracking, so a rule that names a role
and forgets its tracking inherits whatever its parent set: the title and the
selector field once read at body tracking. These pin every rule to its role.
"""

from __future__ import annotations

import re

from infragram.editor import bundle

#: the tracking per role, set for Geist: titles drawn in a little, body and
#: labels at the face's own spacing, the smallest labels opened a hair
TRACKING = {
    "title-large": "-.3px",
    "title-medium": "-.15px",
    "title-small": "-.1px",
    "body-large": "0",
    "body-medium": "0",
    "body-small": "0",
    "label-large": "0",
    "label-medium": ".1px",
    "label-small": ".1px",
}


def _blocks():
    for path in bundle.STYLE_ORDER:
        text = (bundle.UI / path).read_text(encoding="utf-8")
        for selector, body in re.findall(r"([^{}]*)\{([^{}]*)\}", text):
            yield path, selector.strip(), body


def test_the_typeface_is_inter_and_each_role_has_its_tracking() -> None:
    tokens = (bundle.UI / "styles/tokens.css").read_text(encoding="utf-8")
    assert "--md-ref-typeface-brand:'Inter'" in tokens
    assert "--md-ref-typeface-plain:'Inter'" in tokens
    for role, value in TRACKING.items():
        assert f"--md-sys-typescale-{role}-tracking:{value};" in tokens, role
        declared = re.search(rf"--md-sys-typescale-{role}:([^;]+);", tokens).group(1)
        face = "brand" if role.startswith("title") else "plain"
        assert declared.endswith(f"var(--md-ref-typeface-{face})"), role


def test_every_rule_that_names_a_role_sets_that_roles_tracking() -> None:
    missing = []
    for path, selector, body in _blocks():
        roles = re.findall(r"font:var\(--md-sys-typescale-([a-z-]+)\)", body)
        if not roles:
            continue
        assert roles[-1] in TRACKING, f"{path} {selector}: unknown role {roles[-1]}"
        if f"letter-spacing:var(--md-sys-typescale-{roles[-1]}-tracking)" not in body:
            missing.append(f"{path} {selector}")
    assert not missing, "set the role's tracking beside its font:\n" + "\n".join(missing)


def test_no_rule_sets_type_by_hand() -> None:
    loose = []
    for path, selector, body in _blocks():
        if path == "styles/tokens.css":
            continue
        for declaration in re.findall(r"(?:font-family|font-size|letter-spacing):[^;]+", body):
            if declaration in ("letter-spacing:inherit",) or "-tracking)" in declaration:
                continue
            loose.append(f"{path} {selector}: {declaration}")
        for shorthand in re.findall(r"font:([^;]+)", body):
            # a role, inherit, or the one monospace block (template notes) at body-small's size
            if shorthand.startswith("var(--md-sys-typescale-") or shorthand == "inherit":
                continue
            if (
                shorthand.startswith("400 12px/16px 'Geist Mono'")
                and selector == ".template-brief pre"
            ):
                continue
            loose.append(f"{path} {selector}: font:{shorthand}")
    allowed = {"views/inspector/inspector.css .template-brief pre: letter-spacing:0"}
    assert set(loose) <= allowed, "\n".join(sorted(set(loose) - allowed))


def _token_blocks() -> dict[str, dict[str, str]]:
    """Every custom property in tokens.css, by the selector that declares it."""
    text = (bundle.UI / "styles" / "tokens.css").read_text(encoding="utf-8")
    blocks: dict[str, dict[str, str]] = {}
    for selector, body in re.findall(r"([^{}]*)\{([^{}]*)\}", text):
        name = selector.split("*/")[-1].strip()
        blocks.setdefault(name, {}).update(re.findall(r"(--[a-zA-Z0-9-]+):\s*([^;]+)", body))
    return blocks


def test_no_token_is_frozen_to_the_dark_theme_on_root() -> None:
    """A custom property that refers to another resolves where it is declared
    and is inherited as a value, not as a formula.

    ``--md-disabled-content`` was declared on ``:root`` from
    ``--md-sys-color-on-surface``, which is the dark theme's #E0E2EA there. The
    light theme sets its own on-surface on ``body``, but the disabled tokens
    had already been computed: every disabled control in the default light
    theme was pale grey on a pale surface, about 1:1 -- undo and redo at page
    open, the frame review's Icons button, presets with nothing selected.

    So a token that ``:root`` derives from one a theme overrides must be
    derived again wherever that theme is -- or, as the disabled ones are now,
    on ``body``, where every theme sets its colours.
    """
    blocks = _token_blocks()
    root = blocks.get(":root", {})
    overridden = {
        name for selector, props in blocks.items() if selector != ":root" for name in props
    }
    frozen = []
    for name, value in root.items():
        moving = set(re.findall(r"var\((--[a-zA-Z0-9-]+)", value)) & overridden
        rederived = any(name in props for selector, props in blocks.items() if selector != ":root")
        if moving and not rederived:
            frozen.append(f"{name} (from {', '.join(sorted(moving))})")
    assert frozen == [], "derived on :root and never re-derived per theme: " + "; ".join(frozen)


def test_the_disabled_tokens_follow_the_theme() -> None:
    """The two that were frozen are derived on body, where each theme sets
    on-surface -- and from on-surface, so light gets its own dark grey."""
    body = _token_blocks().get("body", {})
    for name in ("--md-disabled-content", "--md-disabled-container"):
        assert name in body, f"{name} is not derived on body"
        assert "var(--md-sys-color-on-surface)" in body[name], body[name]
