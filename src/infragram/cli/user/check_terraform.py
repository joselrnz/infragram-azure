"""``infragram check:terraform``: whether a diagram's Terraform works,
without deploying it.

Terraform itself reads each skeleton, in a copy: ``terraform fmt``, ``init``
and ``validate`` offline, then a plan against mocked providers
(``terraform test``), so nothing is created, no cloud is called and no
credentials are needed (:mod:`infragram.terraform.check`). What it reads:

- a diagram: a ``.infragram.json`` document, a diagram file (``.py``) or an
  exported page (``.html``, the diagram it was exported from), whose
  skeletons are written as the export writes them (``--style``);
- a Terraform folder, as exported or as edited since, or a folder of them
  (an export's output folder).

Each plan, as Terraform prints it, is written to
``<output-dir>/<folder>.plan.txt``.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

__all__ = ["build_parser", "main"]


class _Refused(Exception):
    """A source the command cannot read; nothing is checked."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infragram check:terraform",
        description="Check that a diagram's Terraform works, without deploying it: terraform fmt, "
        "init and validate offline, then a plan against mocked providers. Nothing is "
        "created and no cloud is called.",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        type=Path,
        metavar="SOURCE",
        help="a .infragram.json document, a diagram file (.py), an exported page "
        "(.html), a Terraform folder, or a folder of them",
    )
    parser.add_argument(
        "--style",
        choices=("both", "resources", "modules"),
        default="both",
        help="for a diagram: its plain resources, the public registry's modules, or both (default)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist"),
        metavar="DIR",
        help="where each plan goes, as <folder>.plan.txt (default: ./dist)",
    )
    parser.add_argument(
        "--keep",
        type=Path,
        default=None,
        metavar="DIR",
        help="keep the checked copies in this new or empty folder: the modules copied "
        "in, the values made up and the mocked test, to run terraform test "
        "there yourself",
    )
    parser.add_argument(
        "--var-file",
        type=Path,
        action="append",
        default=[],
        dest="var_files",
        metavar="FILE",
        help="a .tfvars file with your values, as terraform plan -var-file takes it (repeatable)",
    )
    parser.add_argument(
        "--var",
        action="append",
        default=[],
        dest="variables",
        metavar="NAME=VALUE",
        help="a value, as terraform plan -var takes it (repeatable)",
    )
    parser.add_argument(
        "--plugin-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="the provider plugin folder (default: TF_PLUGIN_CACHE_DIR, else the "
        "Terraform CLI configuration's plugin_cache_dir, else Infragram's cache)",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="first download the registry modules and the providers Infragram's "
        "Terraform uses into the caches (network access, once; nothing is "
        "deployed)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from ...iso3d.cache import cache_root
    from ...terraform.check import (
        VALUES_FILE,
        CheckError,
        ConfigurationCheck,
        check_configuration,
        fetch,
        terraform_cli,
    )

    options = build_parser().parse_args(argv)
    for item in options.variables:
        name, sep, _value = item.partition("=")
        if not sep or not name.strip():
            print(f"ERROR: --var takes NAME=VALUE, not {item!r}", file=sys.stderr)
            return 2
    for file in options.var_files:
        if not file.is_file():
            print(f"ERROR: --var-file {file} is not a file", file=sys.stderr)
            return 2
    keep: Path | None = options.keep
    if keep is not None:
        refused = _keep_refused(keep, options.sources)
        if refused:
            print(f"ERROR: {refused}", file=sys.stderr)
            return 2
    try:
        with (
            terraform_cli(options.plugin_dir) as cli,
            tempfile.TemporaryDirectory(prefix="infragram-check-terraform-") as scratch,
        ):
            work = keep or Path(scratch)
            work.mkdir(parents=True, exist_ok=True)
            try:
                configurations = _gather(options.sources, options.style, work)
            except _Refused as error:
                print(f"ERROR: {error}", file=sys.stderr)
                return 2
            if options.fetch:
                cli.plugins = cli.plugins or cache_root() / "terraform" / "plugins"
                fetched = fetch(cli, cli.plugins)
                print(
                    f"FETCHED  {len(fetched)} registry modules, and the providers they and the "
                    f"clouds need, into the module cache and {cli.plugins}"
                )
            print(
                f"TERRAFORM {'.'.join(map(str, cli.version))}, providers from "
                f"{cli.plugins or 'no plugin folder'}, offline"
            )
            results = []
            for folder, original, name in configurations:
                try:
                    result = check_configuration(
                        folder,
                        cli,
                        original=original,
                        var_files=options.var_files,
                        variables=options.variables,
                        name=name,
                    )
                except OSError as error:
                    # one folder that cannot be read or copied fails alone
                    result = ConfigurationCheck(name=name, failed="copy", message=str(error))
                results.append(result)
                _report(result, options.output_dir, cli.plugins)
            if keep is not None:
                print(
                    f"KEPT     {keep}: to plan one again, in its folder: terraform init -backend=false, "
                    f"then terraform test -verbose -var-file={VALUES_FILE}"
                )
    except CheckError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    planned = sum(result.planned for result in results)
    failed = sum(bool(result.failed) for result in results)
    if planned == len(results):
        print(
            f"OK       {planned} configuration{'s' * (planned != 1)} valid and planned against mocked "
            "providers: nothing was created and no cloud was called"
        )
        return 0
    print(
        f"{'FAIL' if failed else 'SKIP':8} {planned} of {len(results)} planned; "
        f"{failed} failed, {len(results) - planned - failed} not checked"
    )
    return 1 if failed else 2


def _keep_refused(keep: Path, sources: list[Path]) -> str:
    """Why ``--keep`` cannot be written to, or nothing."""
    if keep.exists() and (not keep.is_dir() or any(keep.iterdir())):
        return f"--keep {keep} is not a new or empty folder"
    where = keep.resolve()
    for source in sources:
        if source.is_dir() and (source.resolve() == where or source.resolve() in where.parents):
            return f"--keep {keep} is inside {source}, which is copied into it"
    return ""


def _gather(sources: list[Path], style: str, work: Path) -> list[tuple[Path, Path | None, str]]:
    """Every configuration to check, written or copied into ``work``, the
    folder each was copied from (``None`` for a skeleton written here), and
    what it is called: a folder's name, an environment's as
    ``<skeleton>/<environment>``."""
    from ...terraform import TerraformError, folder_name, terraform_files, write_files
    from ...terraform.check import copy_configuration

    styles = ("resources", "modules") if style == "both" else (style,)
    found: list[tuple[Path, Path | None, str]] = []
    for source in sources:
        if source.is_dir():
            for folder in _terraform_folders(source):
                # "." has no name of its own; the folder it is does
                name = _name_of(folder)
                copy = copy_configuration(folder, _unique(work / name.replace("/", "-")))
                found.append((copy, folder, name))
            continue
        if not source.is_file():
            raise _Refused(f"{source} is neither a file nor a folder")
        project = _diagram(source)
        for name in styles:
            try:
                _plan, files = terraform_files(project, name)
            except TerraformError as error:
                raise _Refused(f"{source}: {error}") from error
            folder = _unique(work / folder_name(project.slug, name))
            write_files(files, folder)
            # the environments are the same modules: the one with the diagram's values is checked
            found.append((folder / "environments" / "prod", None, f"{folder.name}/prod"))
    return found


def _name_of(folder: Path) -> str:
    """A configuration's name: an environment's with its skeleton's."""
    folder = folder.resolve()
    if folder.parent.name == "environments":
        return f"{folder.parent.parent.name}/{folder.name}"
    return folder.name


def _terraform_folders(path: Path) -> list[Path]:
    """The folder, when it holds Terraform; a skeleton's environments; else
    each folder in it that does, or is a skeleton."""
    from ...terraform.layout import environment_folders

    if any(path.glob("*.tf")):
        return [path]
    if environment_folders(path):
        return environment_folders(path)
    inner: list[Path] = []
    for child in sorted(path.iterdir()):
        if child.is_dir() and any(child.glob("*.tf")):
            inner.append(child)
        elif child.is_dir():
            inner += environment_folders(child)
    if not inner:
        diagrams = sorted(
            item.name
            for item in path.iterdir()
            if item.name.endswith((".infragram.json", ".html")) or item.suffix == ".py"
        )
        hint = (
            f"; it holds diagrams ({', '.join(diagrams[:3])}{', ...' if len(diagrams) > 3 else ''}): "
            "pass one of them, and its Terraform is written and checked"
            if diagrams
            else ""
        )
        raise _Refused(f"{path} holds no Terraform (*.tf files), nor does any folder in it{hint}")
    return inner


def _diagram(source: Path):
    """The diagram a document, a diagram file or an exported page holds."""
    from ...editor.shell import project_from_html
    from ...exports import ExportError
    from ...projects import CloudProject

    try:
        if source.suffix == ".py":
            from .compose import project_from_spec

            return project_from_spec(source)
        if source.suffix.lower() in (".html", ".htm"):
            # the diagram, not the Terraform text the page carries: a page
            # from someone else is checked as the export writes it
            return project_from_html(source.read_text(encoding="utf-8"))
        return CloudProject.load(source)
    except (ExportError, ValueError, OSError) as error:
        raise _Refused(f"{source}: {error}") from error


def _unique(path: Path) -> Path:
    """``path``, or ``path-2``, ``path-3``... when two sources share a name."""
    candidate, n = path, 1
    while candidate.exists():
        n += 1
        candidate = path.with_name(f"{path.name}-{n}")
    return candidate


def _report(result, output_dir: Path, plugins: Path | None) -> None:
    """Print what Terraform said of one configuration, and write its plan."""
    steps = [f"fmt {'ok' if not result.reformat else 'differs'}"]
    if result.failed in ("fmt", "copy"):
        steps = [f"{result.failed} FAIL"]
    elif not result.missing:
        for step in ("init", "validate", "plan"):
            if result.failed == step:
                steps.append(f"{step} FAIL")
                break
            if step == "plan" and not result.planned:
                steps.append("plan not run")
                break
            steps.append(f"{step} ok")
    label = "PASS" if result.planned else "FAIL" if result.failed else "SKIP"
    created = (
        f" ({result.to_create} to create)"
        if result.planned and result.to_create is not None
        else ""
    )
    print(f"{label:8} {result.name}: {', '.join(steps)}{created}", flush=True)
    if result.failed:
        print(
            f"{'':8} "
            + (
                "the folder could not be copied to check:"
                if result.failed == "copy"
                else f"terraform {result.failed} says:"
            )
        )
        for line in result.message.splitlines():
            print(f"{'':10}{line}")
    if result.missing:
        where = f"{plugins} or the module cache" if plugins is not None else "any plugin folder"
        print(
            f"{'':8} not run: {', '.join(result.missing)} not in {where}; --fetch downloads what "
            "Infragram's Terraform uses, --plugin-dir names another folder"
        )
    if result.unplanned:
        print(f"{'':8} not planned: {result.unplanned}")
    if result.reformat:
        print(
            f"NOTE     terraform fmt would lay out {', '.join(result.reformat)} otherwise "
            "(terraform fmt -recursive does)"
        )
    if result.made_up:
        shown = ", ".join(result.made_up[:6]) + (
            f" and {len(result.made_up) - 6} more" if len(result.made_up) > 6 else ""
        )
        print(
            f"NOTE     made-up values for {len(result.made_up)} variable{'s' * (len(result.made_up) != 1)} "
            f"nothing gave: {shown} (--var-file gives yours)"
        )
    if result.plan_text:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{result.name.replace('/', '-')}.plan.txt"
        header = [
            f"# infragram check:terraform: {result.name}",
            "# A plan against mocked providers (terraform test): nothing was created and no "
            "cloud was called.",
            f"# Mocked: {', '.join(result.mocked) or 'nothing'}",
            f"# Made-up values: {', '.join(result.made_up) or 'none'}",
            "",
            "",
        ]
        path.write_text("\n".join(header) + result.plan_text + "\n", encoding="utf-8", newline="\n")
        print(f"PLAN     {path}")
