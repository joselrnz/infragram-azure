#!/usr/bin/env python3
"""Terraform itself accepts the skeleton of every shipped template.

For each template that draws on AWS, Azure or Google Cloud, and for each
cloud's coverage diagram (one of each component its table writes,
``infragram.terraform.coverage``), both skeletons the export writes,
``terraform`` (plain resources) and ``terraform-modules`` (the public
registry's modules where one fits), are read by the Terraform CLI:

- ``terraform fmt -check`` on every one, so the writer lays HCL out as fmt does;
- ``terraform init -backend=false`` and ``terraform validate``, offline, on every
  skeleton whose providers are all in the plugin folder; a modules skeleton's
  registry modules are copied from the module cache into it and called there
  by path, so ``init`` reads them without the network;
- with ``--plan``, ``terraform test`` plans each one against mocked providers
  (``mock_provider``), every variable the diagram leaves to fill given a value
  of its shape: what ``validate`` cannot see fails there -- a registry
  module's own validation rules, a name longer than the provider takes, an
  attribute a map's type drops, a root output that reads a sensitive value.

The checks are the package's (``infragram.terraform.check``), which the user
command ``infragram check:terraform`` runs on a diagram of the user's own.

The plugin folder is ``--plugin-dir``, else ``TF_PLUGIN_CACHE_DIR``, else
``<cache>/terraform/plugins``. A provider missing from it is named in the
report, and the skeletons that need it are only format-checked. Nothing is
downloaded unless ``--fetch`` asks: then ``terraform init`` first downloads
the registry modules ``assets/terraform/modules.json`` pins, and the
providers they need, into the module cache (``<cache>/terraform/modules``,
which the import reads) and the plugin folder. The providers are installed
once into the Infragram cache (``<cache>/terraform``) and reused.

It needs the Terraform CLI, which CI does not have, so ``verify:all`` does not
run it: run it after a change to ``src/infragram/terraform/`` or
``assets/terraform/``, and before a release.

    python -m infragram verify:terraform [--plugin-dir DIR] [--keep DIR] [--fetch] [--plan]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))

from infragram.iso3d.cache import cache_root  # noqa: E402
from infragram.projects import CloudProject  # noqa: E402
from infragram.terraform import TerraformError, write_terraform  # noqa: E402
from infragram.terraform.check import (  # noqa: E402
    CheckError,
    Terraform,
    check_configuration,
    fetch,
    terraform_cli,
)
from infragram.terraform.coverage import coverage_project  # noqa: E402
from infragram.terraform.mapping import PROVIDERS  # noqa: E402

TEMPLATES = ROOT / "skills" / "infragram-azure" / "assets" / "templates" / "cloud"


def _check(cli: Terraform, options: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="infragram-terraform-") as scratch:
        out = options.keep or Path(scratch)
        failures: list[str] = []
        formatted: list[str] = []
        validated: list[str] = []
        planned: list[str] = []
        unvalidated: dict[str, list[str]] = {}
        projects = [CloudProject.load(path) for path in sorted(TEMPLATES.glob("*.infragram.json"))]
        # and one of each component every table writes, not only what the templates draw
        projects += [coverage_project(provider) for provider in PROVIDERS]
        skeletons: list[Path] = []
        for project in projects:
            for style in ("resources", "modules"):
                try:
                    skeletons.append(
                        write_terraform(project, out, overwrite=True, style=style).directory
                    )
                except TerraformError:
                    continue
        for skeleton in skeletons:
            slug = skeleton.name
            # the modules are formatted as the environments are; the environment's
            # own check reads them through copies it does not format
            whole = cli.run(["fmt", "-check", "-recursive", "-list=true", "-no-color"], skeleton)
            listed = [line.strip() for line in whole.stdout.splitlines() if line.strip()]
            if whole.returncode or listed:
                failures.append(
                    f"{slug}: terraform fmt would change {listed or whole.stderr.strip()}"
                )
                continue
            # the environments are the same modules: prod, with the diagram's values, is planned
            result = check_configuration(
                skeleton / "environments" / "prod", cli, plan=options.plan, name=f"{slug}/prod"
            )
            if result.failed == "fmt" or result.reformat:
                failures.append(
                    f"{slug}: terraform fmt would change {result.reformat or result.message}"
                )
                continue
            formatted.append(slug)
            if result.missing:
                for what in result.missing:
                    unvalidated.setdefault(what, []).append(slug)
                continue
            if result.failed in ("init", "validate"):
                failures.append(f"{slug}: terraform {result.failed} failed\n{result.message}")
                continue
            validated.append(slug)
            if not options.plan:
                continue
            if result.failed == "plan":
                failures.append(
                    f"{slug}: terraform test (a plan against mocked providers) failed\n{result.message}"
                )
            elif result.unplanned:
                failures.append(f"{slug}: not planned: {result.unplanned}")
            else:
                planned.append(slug)

    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    for what, slugs in unvalidated.items():
        where = (
            f"in {cli.plugins} or the module cache"
            if cli.plugins is not None
            else "anywhere (no plugin folder: TF_PLUGIN_CACHE_DIR is unset)"
        )
        print(f"NOTE {what} is not {where}, so these are format-checked only: {', '.join(slugs)}")
    if failures:
        return 1
    print(
        f"OK terraform: {len(formatted)} skeletons as terraform fmt writes them, "
        f"{len(validated)} valid to terraform validate"
        + (f", {len(planned)} planned against mocked providers" if options.plan else "")
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="infragram verify:terraform", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--plugin-dir",
        type=Path,
        default=None,
        help="the provider plugin folder (default: TF_PLUGIN_CACHE_DIR)",
    )
    parser.add_argument(
        "--keep",
        type=Path,
        default=None,
        help="write the skeletons here and keep them (default: a temporary folder)",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="first download the registry modules the export pins, and their providers "
        "(network access; the module cache and the plugin folder keep them)",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="also plan each valid skeleton against mocked providers (terraform test): "
        "what validate cannot see, such as a module's own validation rules",
    )
    options = parser.parse_args(argv)
    try:
        with terraform_cli(options.plugin_dir) as cli:
            if options.fetch:
                cli.plugins = cli.plugins or cache_root() / "terraform" / "plugins"
                for fetched in fetch(cli, cli.plugins):
                    print(f"FETCHED {fetched}")
            return _check(cli, options)
    except CheckError as error:
        print(f"FAIL terraform: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
