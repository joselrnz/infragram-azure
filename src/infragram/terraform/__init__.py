"""A diagram into a modular Terraform skeleton: the export's ``terraform`` format.

``write_terraform(project, output_dir)`` writes ``<output_dir>/<slug>-terraform/``
the way a Terraform repository is laid out (:mod:`.layout`): a module a
concern under ``modules/`` (network, security, compute...), each holding the
resources the diagram draws for it, and ``environments/dev`` and
``environments/prod``, each calling every module once with its own state.
Every value the diagram does not state is a variable; those without a
default are listed in each environment's ``terraform.tfvars.example`` and the
README, beside every wire and how it was written and every element that
became no resource, and why. ``style="modules"`` writes the same layout
through the public registry's modules where one fits.

Azure is written; see ``references/terraform.md``.
The export's ``terraform`` format (``--formats terraform``) is this function
run beside the pictures, through the same staging folder.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from pydantic import Field

from ..exports.errors import ExportError
from ..projects import CloudProject
from .emit import Plan, Variable, Wire, plan_terraform
from .model import Record

__all__ = [
    "TerraformError",
    "TerraformResult",
    "plan_terraform",
    "render_plan",
    "summary",
    "terraform_files",
    "write_files",
    "write_terraform",
    "write_zip",
]


class TerraformError(ExportError):
    """The skeleton cannot be written: the diagram draws nothing the export
    writes, or the folder exists."""


class TerraformResult(Record):
    directory: Path
    files: list[Path] = Field(default_factory=list)
    todos: list[Variable] = Field(default_factory=list)
    not_written: list[tuple[str, str]] = Field(default_factory=list)
    wires: list[Wire] = Field(default_factory=list)
    #: element id -> what the skeleton calls it (``web``, ``vpc``)
    nouns: dict[str, str] = Field(default_factory=dict)


def render_plan(plan: Plan) -> dict[str, str]:
    """Every file of the skeleton, relative path -> text: a module a concern
    under ``modules/``, composed by ``environments/dev`` and ``environments/prod``."""
    from .layout import render_layout

    return render_layout(plan)


def terraform_files(project: CloudProject, style: str = "resources") -> tuple[Plan, dict[str, str]]:
    """The plan and every file of the skeleton, relative path -> text, in
    plain resources or (``style="modules"``) the registry's modules where one
    fits.

    Refused with :class:`TerraformError` when the diagram draws nothing on
    Azure: an empty skeleton would say nothing.
    """

    plan = plan_terraform(project, style)
    if not plan.providers:
        raise TerraformError(
            f"{project.title} draws nothing on Azure, "
            "the cloud this edition's Terraform export writes"
        )
    return plan, render_plan(plan)


def write_files(files: dict[str, str], directory: Path) -> None:
    """Write :func:`terraform_files`' texts under ``directory``."""

    for relative, text in files.items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def write_zip(files: dict[str, str], path: Path, folder: str) -> None:
    """Write :func:`terraform_files`' texts into one ``.zip`` at ``path``,
    each under ``folder/``, as the exported page's Download menu lays it out.
    The entries are sorted and dated 1980-01-01, so the same skeleton makes
    the same bytes."""

    import zipfile

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(files):
            entry = zipfile.ZipInfo(f"{folder}/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr = 0o644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, files[relative].encode("utf-8"))


def summary(plan: Plan) -> str:
    """One line on what the skeleton leaves to its reader."""

    todos = sum(1 for v in plan.root.variables.values() if v.todo)
    return (
        f"{todos} variable{'s' * (todos != 1)} to fill (terraform.tfvars.example) and "
        f"{len(plan.not_written)} element{'s' * (len(plan.not_written) != 1)} written as no "
        "resource; its README.md says which and why"
    )


def folder_name(slug: str, style: str = "resources") -> str:
    """``<slug>-terraform``, or ``<slug>-terraform-modules`` for the modules style."""
    return f"{slug}-terraform" if style == "resources" else f"{slug}-terraform-modules"


def write_terraform(
    project: CloudProject, output_dir: Path, *, overwrite: bool = False, style: str = "resources"
) -> TerraformResult:
    """Write the skeleton to ``<output_dir>/<slug>-terraform/`` (or
    ``<slug>-terraform-modules/`` in the modules style).

    The folder is written whole or not at all: drawn into a staging folder
    beside it, then moved into place. An existing folder is refused unless
    ``overwrite``, and then replaced whole.
    """

    output_dir = Path(output_dir)
    final = output_dir / folder_name(project.slug, style)
    if final.exists() and not overwrite:
        raise TerraformError(f"{final} exists; pass --force to replace it")
    plan, files = terraform_files(project, style)
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}-", dir=output_dir))
    try:
        write_files(files, staging / final.name)
        if final.exists():
            os.replace(final, staging / ".replaced")
        os.replace(staging / final.name, final)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    todos = [v for v in plan.root.variables.values() if v.todo]
    return TerraformResult(
        final,
        sorted(final / relative for relative in files),
        todos,
        plan.not_written,
        plan.wires,
        plan.element_nouns,
    )
