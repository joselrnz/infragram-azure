"""Build the price tables the export prices from with no network.

Each cloud's builder reads its public price source (kept in the build cache,
so a rerun reads the network once; ``--fresh`` reads it again) and writes
skills/infragram-azure/assets/prices/<cloud>.json:

- aws: the AWS Price List API (pricing.us-east-1.amazonaws.com) and the
  calculator's EC2 price files (b0.p.awsstatic.com), no sign-in
- azure: the Azure Retail Prices API (prices.azure.com), no sign-in
- gcp: the Cloud Billing Catalog API (cloudbilling.googleapis.com), which
  needs an API key in INFRAGRAM_GCP_PRICING_KEY

usage: price-tables.py aws|azure|gcp|all [--fresh]
       price-tables.py --check     # every shipped table loads, and every
                                   # pricer's services are in it
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infragram.pricing import PricingError  # noqa: E402
from infragram.pricing.tables import load_table, tables_dir  # noqa: E402

CLOUDS = ("aws", "azure", "gcp")
#: A table older than this is still used, and the check says so.
STALE_DAYS = 90


def check() -> int:
    problems = []
    for cloud in CLOUDS:
        path = tables_dir() / f"{cloud}.json"
        if not path.is_file():
            print(f"NOTE {cloud}: no table shipped ({path.name}); its components stay unpriced")
            continue
        try:
            table = load_table(cloud)
        except PricingError as error:
            problems.append(f"{cloud}: {error}")
            continue
        age = (datetime.date.today() - datetime.date.fromisoformat(table.read)).days
        size = path.stat().st_size
        print(
            f"OK {cloud}: {len(table.services)} services, read {table.read} "
            f"({age} days ago), {size / 1e6:.1f} MB"
        )
        if age > STALE_DAYS:
            print(f"NOTE {cloud}: the table is over {STALE_DAYS} days old; rebuild it")
    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("cloud", nargs="?", choices=(*CLOUDS, "all"))
    parser.add_argument("--fresh", action="store_true", help="read every source again")
    parser.add_argument("--check", action="store_true", help="check the shipped tables")
    options = parser.parse_args(argv)
    if options.check or not options.cloud:
        return check()
    for cloud in CLOUDS if options.cloud == "all" else (options.cloud,):
        builder = importlib.import_module(f"infragram.pricing.build.{cloud}")
        path = builder.build(fresh=options.fresh)
        print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
    load_table.cache_clear()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
