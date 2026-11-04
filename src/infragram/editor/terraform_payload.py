"""The diagram's Terraform, carried in the page for its download menu.

The export writes a diagram's Terraform skeleton (:mod:`infragram.terraform`);
the page cannot write one, so the page is given it: every style, exactly as
the ``terraform`` and ``terraform-modules`` formats write it, from the
document the page is drawn from, deflated the way the library travels. The
download menu offers one item a style (``ui/views/header.py``) and the
runtime zips that folder when it is chosen (``runtime/29-downloads.js``). A
diagram with nothing on the clouds the export writes for carries none, and
its page offers none.
"""

from __future__ import annotations

import base64
import json
import re
import zlib

from ..projects import CloudProject

#: How the payload travels: the library's own encoding (``shell.LIBRARY_ENCODING``),
#: which the runtime's ``readEmbeddedJson`` inflates.
ENCODING = "deflate-raw;base64"

_SCRIPT = re.compile(
    r'<script type="application/octet-stream" id="infragram-terraform"[^>]*>(.*?)</script>',
    re.S,
)


def terraform_payload(project: CloudProject) -> dict[str, dict[str, object]]:
    """The skeleton in each style: style -> ``{"folder": <folder name>,
    "files": {path: text}}``, or ``{}`` for a diagram the export writes no
    Terraform for."""
    # Imported here: the Terraform package reaches the exports package, which
    # imports the editor to draw its pages.
    from ..terraform import TerraformError, folder_name, terraform_files
    from ..terraform.emit import STYLES

    payload: dict[str, dict[str, object]] = {}
    for style in STYLES:
        try:
            _plan, files = terraform_files(project, style)
        except TerraformError:
            return {}
        payload[style] = {"folder": folder_name(project.slug, style), "files": files}
    return payload


def terraform_script(project: CloudProject) -> tuple[tuple[str, ...], str]:
    """The styles the page offers and the ``<script>`` element carrying them,
    or ``((), "")`` when there is nothing to carry."""
    payload = terraform_payload(project)
    if not payload:
        return (), ""
    packer = zlib.compressobj(9, zlib.DEFLATED, -15)
    text = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    blob = base64.b64encode(packer.compress(text) + packer.flush()).decode("ascii")
    return tuple(payload), (
        f'<script type="application/octet-stream" id="infragram-terraform" '
        f'data-encoding="{ENCODING}">{blob}</script>'
    )


def terraform_from_html(html: str) -> dict[str, dict[str, object]]:
    """The Terraform a rendered page carries, as :func:`terraform_payload`
    gives it, or ``{}`` for a page that carries none."""
    match = _SCRIPT.search(html)
    if match is None:
        return {}
    return json.loads(
        zlib.decompress(base64.b64decode(match.group(1).strip()), -15).decode("utf-8")
    )


__all__ = ["ENCODING", "terraform_from_html", "terraform_payload", "terraform_script"]
