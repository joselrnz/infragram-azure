"""``infragram import:terraform`` and ``infragram discover:<cloud>``: a diagram of
what already exists.

Both end the same way: the estate is drawn (:func:`infragram.estate.draw`),
written as a diagram file the user edits (``<slug>.py``) beside a report of
every resource and where it went (``<slug>.import.md``), and the diagram file
is composed and exported like any other (``--formats``, ``--verify``, ...).

- ``import:terraform <folder>`` reads a configuration's files; ``<plan.json>``
  or ``terraform.tfstate`` reads what Terraform itself reported.
- ``discover:azure`` and ``discover:kubernetes`` read a live estate through
  ``az`` or ``kubectl``, signed in as the user, with list and get calls
  only: nothing is created, changed or deleted.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from collections.abc import Callable
from pathlib import Path

from .options import add_export_options

__all__ = [
    "discover_azure",
    "discover_kubernetes",
    "import_terraform",
    "write_drawing",
]


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--title", default=None, metavar="TEXT", help="the diagram's title (default: what was read)"
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=None,
        metavar="FILE",
        help="where the diagram file goes (default: <output-dir>/<slug>.py)",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="write the diagram file and the report only, without drawing them",
    )
    parser.add_argument(
        "--comment",
        type=Path,
        default=None,
        metavar="FILE",
        help="also write a Markdown summary for a pull request comment: a plan's changes, or "
        "for a diagram import what was drawn and what was guessed",
    )
    add_export_options(parser, libraries="drawn", title=False)


def _finish(estate, options: argparse.Namespace, command: str, drawing=None) -> int:
    """Draw (unless the reader drew it), write the diagram file and report,
    then compose and export it."""
    from ...estate import draw
    from ...estate.report import write_report

    if options.title:
        estate.title = options.title
        if drawing is not None:
            drawing.title = options.title
    drawing = drawing if drawing is not None else draw(estate)
    if not drawing.drawn:
        where = "in Kubernetes" if drawing.thing == "object" else "on Azure"
        print(
            f"ERROR: {estate.origin} holds nothing {where} to draw "
            f"({len(estate.resources)} {drawing.thing}s read)",
            file=sys.stderr,
        )
        return 2
    if getattr(options, "comment", None):
        from ...estate.comment import plan_comment
        from ...exports.written import write_side_file

        try:
            write_side_file(
                options.comment,
                plan_comment(estate, drawing),
                force=getattr(options, "force", False),
            )
        except (OSError, ValueError) as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
        print(f"COMMENT  {options.comment}")
    return write_drawing(
        drawing,
        options,
        command,
        read=f"{len(estate.resources)} resources from {estate.origin}",
        report=lambda spec, date: write_report(
            estate, drawing, command=command, date=date, spec=spec
        ),
    )


def shown(path: Path) -> str:
    """A source path as the diagram file and report record it: relative to
    the folder the command ran in when it is inside it, else its name alone.
    The command line is written into files that get committed and shared; an
    absolute path would carry the importing machine's user and folders."""
    import os

    if not path.is_absolute():
        return path.as_posix()
    try:
        relative = Path(os.path.relpath(path, Path.cwd()))
    except ValueError:  # another drive
        return path.name
    return relative.as_posix() if not relative.as_posix().startswith("../") else path.name


def write_drawing(
    drawing,
    options: argparse.Namespace,
    command: str,
    *,
    read: str,
    report: Callable[[str, str], str],
    spec: Path | None = None,
) -> int:
    """Write a drawing's diagram file and report (``report(spec name, date)``),
    then compose and export it as the options say. Every import ends here."""
    from ...author.diagram import slugify
    from ...estate import SpecError, write_spec
    from ...exports import written

    slug = slugify(drawing.title)
    spec = spec or options.spec or options.output_dir / f"{slug}.py"
    report_path = spec.with_name(f"{spec.stem}.import.md")
    # A diagram file or report this import wrote and nobody has edited since
    # is replaced; a hand-edited one needs --force, so its edits are not lost.
    existing = written.blocking((spec, report_path))
    if existing and not options.force:
        print(
            "ERROR: refusing to overwrite files edited since they were imported, or not "
            "imported here (pass --force to replace them): "
            + ", ".join(str(path) for path in existing),
            file=sys.stderr,
        )
        return 2
    # Corrections kept beside the diagram file survive every re-import
    # (estate/overrides.py), so the file itself never needs a hand edit.
    from ...estate.overrides import apply_overrides, overrides_path

    corrections = overrides_path(spec)
    if corrections.is_file():
        applied, notes = apply_overrides(drawing, corrections)
        drawing.notes += notes
        print(f"OVERRIDE {applied} rule(s) from {corrections.name}")
    date = datetime.date.today().isoformat()
    try:
        text = write_spec(drawing, command=command, date=date, filename=spec.name)
    except SpecError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(text, encoding="utf-8", newline="\n")
    report_path.write_text(report(spec.name, date), encoding="utf-8", newline="\n")
    written.remember((spec, report_path))
    print(f"READ     {read}")
    print(
        f"SPEC     {spec} ({len(drawing.drawn)} {drawing.thing}{'' if len(drawing.drawn) == 1 else 's'} "
        f"drawn, {len(drawing.wires)} wire{'' if len(drawing.wires) == 1 else 's'})"
    )
    print(f"REPORT   {report_path}")
    for note in dict.fromkeys(drawing.notes):
        print(f"NOTE     {note}", file=sys.stderr)
    if options.no_export:
        return 0
    from .compose import project_from_spec
    from .export_project import run_export

    project = project_from_spec(spec)
    print(
        f"PROJECT  {project.slug} | {project.kind} | {', '.join(project.provider_ids)} | "
        f"{len(project.topology.index())} elements"
    )
    return run_export(project, options)


# ------------------------------------------------------------ import:terraform
def _terraform_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infragram import:terraform",
        description="Draw what a Terraform configuration, plan or state declares: an editable "
        "diagram file, a report of every resource, and the diagram exported.",
    )
    parser.add_argument(
        "source",
        type=Path,
        help="a configuration's folder, a plan or state as `terraform show -json` "
        "writes it, or a terraform.tfstate file",
    )
    parser.add_argument(
        "--var-file",
        type=Path,
        action="append",
        default=[],
        dest="var_files",
        metavar="FILE",
        help="a .tfvars file, as terraform plan -var-file takes it (repeatable)",
    )
    parser.add_argument(
        "--var",
        action="append",
        default=[],
        dest="variables",
        metavar="NAME=VALUE",
        help="a variable's value, as terraform plan -var takes it (repeatable)",
    )
    _common(parser)
    return parser


def import_terraform(argv: list[str] | None = None) -> int:
    from ...terraform.readconfig import ConfigurationError, read_configuration
    from ...terraform.readstate import StateError, read_show_json

    options = _terraform_parser().parse_args(argv)
    values: dict[str, str] = {}
    for item in options.variables:
        name, sep, value = item.partition("=")
        if not sep or not name:
            print(f"ERROR: --var takes NAME=VALUE, not {item!r}", file=sys.stderr)
            return 2
        values[name.strip()] = value
    source: Path = options.source
    try:
        if source.is_dir():
            estate = read_configuration(source, var_files=options.var_files, values=values)
        elif source.is_file():
            if options.var_files or values:
                print(
                    "NOTE     --var and --var-file apply to a configuration's folder; "
                    "a plan or state already holds its values",
                    file=sys.stderr,
                )
            estate = read_show_json(source)
        else:
            print(f"ERROR: {source} is neither a folder nor a file", file=sys.stderr)
            return 2
    except (ConfigurationError, StateError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return _finish(estate, options, f"import:terraform {shown(source)}")


# ------------------------------------------------------------ discover:<cloud>
def _discover_parser(cloud: str, where: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"infragram discover:{cloud}",
        description=f"Draw a live {where} estate, read-only through its CLI as you are signed in: "
        "an editable diagram file, a report of every resource, and the diagram exported.",
    )
    return parser


def _discover(cloud: str, argv: list[str] | None) -> int:
    from ...estate.discover import DiscoveryError

    if cloud == "azure":
        parser = _discover_parser("azure", "Azure")
        parser.add_argument(
            "--subscription",
            default=None,
            metavar="ID",
            help="the subscription to read (default: the CLI's current one)",
        )
        parser.add_argument(
            "--resource-group",
            action="append",
            default=[],
            dest="groups",
            metavar="NAME",
            help="read only this resource group (repeatable)",
        )
        parser.add_argument(
            "--source",
            choices=("cli", "resource-graph"),
            default="cli",
            help="how to read it: cli, one az list call per kind of resource (default), or "
            "resource-graph, one paged Azure Resource Graph query through az rest; the "
            "drawing is the same either way",
        )
    elif cloud == "kubernetes":
        parser = _discover_parser("kubernetes", "Kubernetes")
        parser.description = (
            "Draw a live Kubernetes cluster, read-only through kubectl as the kubeconfig signs "
            "in: namespaces as frames, workloads with what they made folded in, and the wires "
            "the objects name (ingress to service, service to workload, claims, autoscalers)."
        )
        parser.add_argument(
            "--context",
            default=None,
            metavar="NAME",
            help="the kubeconfig context to read (default: the current one)",
        )
        parser.add_argument(
            "--namespace",
            action="append",
            default=[],
            dest="namespaces",
            metavar="NAME",
            help="read only this namespace (repeatable; default: every namespace)",
        )
        parser.add_argument(
            "--include-system",
            action="store_true",
            help="also draw kube-system, kube-public and kube-node-lease",
        )
    else:
        raise ValueError(f"no discover:{cloud} in this edition")
    _common(parser)
    options = parser.parse_args(argv)
    try:
        if cloud == "kubernetes":
            from ...estate.discover.kubernetes import (
                discover_kubernetes as read_cluster,
                draw_cluster,
            )

            estate = read_cluster(context=options.context, namespaces=options.namespaces)
            command = "discover:kubernetes" + (
                f" --context {options.context}" if options.context else ""
            )
            command += "".join(f" --namespace {name}" for name in options.namespaces)
            drawing = draw_cluster(estate, include_system=options.include_system)
            return _finish(estate, options, command, drawing)
        if options.source == "resource-graph":
            from ...estate.discover.azure_graph import discover_azure_graph as read_azure
        else:
            from ...estate.discover.azure import discover_azure as read_azure

        estate = read_azure(subscription=options.subscription, groups=options.groups)
        command = "discover:azure" + (
            f" --subscription {options.subscription}" if options.subscription else ""
        )
        if options.source == "resource-graph":
            command += " --source resource-graph"
    except DiscoveryError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return _finish(estate, options, command)


def discover_azure(argv: list[str] | None = None) -> int:
    return _discover("azure", argv)


def discover_kubernetes(argv: list[str] | None = None) -> int:
    return _discover("kubernetes", argv)
