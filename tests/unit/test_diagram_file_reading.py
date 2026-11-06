"""Reading a diagram file never runs it, and the file cannot stop the read.

The check hook reads every diagram file an agent writes. It imports only the
infragram package's own modules to see what they define; the package's
``__main__`` is the command line, which acts when imported, so a file naming
it must not be able to end the check early.
"""

from __future__ import annotations

from pathlib import Path

from infragram.compose.diagram_file import static_findings

DIAGRAM = """\
import infragram.__main__
from infragram.nodes.azure.compute import NoSuchThing
from infragram.author import Diagram

with Diagram("x", "y"):
    NoSuchThing("a")
"""


def test_a_file_that_imports_the_command_line_is_still_read_to_the_end() -> None:
    findings = static_findings(Path("diagram.py"), DIAGRAM)
    assert findings is not None
    assert any("NoSuchThing" in finding for finding in findings), findings
