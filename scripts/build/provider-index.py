#!/usr/bin/env python3
"""Build the merged icon index at skills/infragram-azure/assets/icons/index.json.

Thin entry point: the logic lives in :mod:`infragram.builders.index`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir()) / "src"
    ),
)

from infragram.builders.index import build_index


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args(argv)
    out, index = build_index()
    print(f"indexed {index['counts']['total']} icons -> {out}")
    print(f"by domain: {index['counts']['by_domain']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
