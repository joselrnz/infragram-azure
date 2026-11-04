"""Replace mojibake sequences in UTF-8 files with their original characters.

The repo had a few files saved by a tool that interpreted UTF-8 as cp1252 and
re-saved as UTF-8, producing classic mojibake (em-dash becomes an 'a-hat euro'
sequence, the section sign grows a stray 'A-circumflex', and so on). This
script rewrites those sequences in-place without touching legitimately-encoded
UTF-8 elsewhere in the file.

Every sequence is spelled with explicit ``\\uXXXX`` escapes: two of the
corrupted third characters (U+009D and U+0090, from cp1252's undefined
0x9D/0x90 slots) are INVISIBLE control characters that silently disappear from
literal source strings, and the rest are easily-confused lookalikes.
"""

from __future__ import annotations

import sys

# (mojibake sequence, intended character)
PAIRS: list[tuple[str, str]] = [
    ("\u00e2\u20ac\u201d", "\u2014"),  # em-dash
    ("\u00e2\u20ac\u201c", "\u2013"),  # en-dash
    ("\u00e2\u20ac\u2122", "\u2019"),  # right single quote
    ("\u00e2\u20ac\u02dc", "\u2018"),  # left single quote
    ("\u00e2\u20ac\u0153", "\u201c"),  # left double quote
    ("\u00e2\u20ac\u009d", "\u201d"),  # right double quote (third char U+009D is INVISIBLE)
    ("\u00e2\u20ac\u00a6", "\u2026"),  # horizontal ellipsis
    ("\u00e2\u20ac\u00a2", "\u2022"),  # bullet
    ("\u00e2\u2020\u2019", "\u2192"),  # right arrow
    ("\u00e2\u2020\u0090", "\u2190"),  # left arrow (third char U+0090 is INVISIBLE)
    ("\u00e2\u2020\u2018", "\u2191"),  # up arrow
    ("\u00e2\u2020\u201c", "\u2193"),  # down arrow
    ("\u00e2\u2030\u00a4", "\u2264"),  # less-than-or-equal
    ("\u00e2\u2030\u00a5", "\u2265"),  # greater-than-or-equal
    ("\u00c3\u2014", "\u00d7"),  # multiplication sign
    ("\u00c3\u00b7", "\u00f7"),  # division sign
    ("\u00c2\u00a7", "\u00a7"),  # section sign
    ("\u00c2\u00b0", "\u00b0"),  # degree
    ("\u00c2\u00bd", "\u00bd"),  # one-half
    ("\u00c2\u00ab", "\u00ab"),  # left guillemet
    ("\u00c2\u00bb", "\u00bb"),  # right guillemet
    ("\u00c2\u00a9", "\u00a9"),  # copyright
    ("\u00c2\u00ae", "\u00ae"),  # registered
]

# Some cp1252 round-trips drop the undefined 0x9D byte outright, leaving only
# the two-character remnant of a mangled right double quote. This pair must
# run after every longer sequence so it only ever sees leftovers.
FALLBACK_PAIRS: list[tuple[str, str]] = [
    ("\u00e2\u20ac", "\u201d"),  # right-double-quote remnant (dropped 0x9D byte)
]


def ordered_pairs() -> list[tuple[str, str]]:
    """Longest sequences first (defensive), then the short fallback remnants."""
    return sorted(PAIRS, key=lambda pair: len(pair[0]), reverse=True) + FALLBACK_PAIRS


def fix(path: str) -> int:
    """Repair one file in place; return the number of replaced sequences."""
    with open(path, "rb") as handle:
        raw = handle.read()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom:
        raw = raw[3:]
    text = raw.decode("utf-8")
    replaced = 0
    for bad, good in ordered_pairs():
        if bad in text:
            replaced += text.count(bad)
            text = text.replace(bad, good)
    if replaced == 0 and not had_bom:
        print(f"{path}: no mojibake found")
        return 0
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    note = " (also stripped BOM)" if had_bom else ""
    print(f"{path}: replaced {replaced} sequence(s){note}")
    return replaced


def main(argv: list[str]) -> int:
    failures = 0
    for path in argv:
        try:
            fix(path)
        except (UnicodeDecodeError, OSError) as error:
            print(f"{path}: FAILED: {error}", file=sys.stderr)
            failures += 1
    if failures:
        print(f"{failures} file(s) could not be repaired", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
