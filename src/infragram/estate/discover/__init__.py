"""A live estate, read through the provider's own CLI: ``aws``, ``az``, ``gcloud``.

Read-only by construction: every call a reader makes is a list, describe, get
or show, run as the user is already signed in, and each reader's calls are
spelt out in its module. A call the account may not make, or a service that
is not switched on, is a note in the report rather than a failure, so a
partial view is still drawn and says what it could not see.

Each reader turns what it reads into :class:`~infragram.estate.Found` records
in Terraform's own terms (``aws_subnet`` with its ``vpc_id``), so the
drawing step is the one that draws a configuration.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

__all__ = ["CallError", "DiscoveryError", "Runner", "cli_runner", "last_segment", "tags"]

#: Runs one CLI call (without the program name) and returns its parsed JSON.
Runner = Callable[[list[str]], Any]

_INSTALL = {
    "aws": "install the AWS CLI v2 and sign in (aws configure, or aws sso login)",
    "az": "install the Azure CLI and sign in (az login)",
    "gcloud": "install the Google Cloud CLI and sign in (gcloud auth login)",
    "kubectl": "install kubectl and point a kubeconfig context at the cluster",
}


class DiscoveryError(RuntimeError):
    """The estate cannot be read at all: no CLI, not signed in, nothing named."""


class CallError(RuntimeError):
    """One call failed; the reader notes it and goes on."""

    def __init__(self, call: str, message: str) -> None:
        super().__init__(f"{call}: {message}")
        self.call = call
        self.message = message


def cli_runner(program: str, timeout: float = 300) -> Runner:
    """A runner for ``program``, found on the PATH."""
    executable = shutil.which(program)
    if executable is None:
        raise DiscoveryError(
            f"the {program} CLI is not on the PATH; {_INSTALL.get(program, 'install it')}"
        )

    batch = executable.lower().endswith((".cmd", ".bat"))

    def run(args: list[str]) -> Any:
        call = " ".join([program, *args])
        command: str | list[str] = [executable, *args]
        if batch:
            # az and gcloud on Windows: a batch file runs through cmd.exe,
            # which reads & | < > as commands where the C runtime's quoting
            # (what Python writes) does not protect them
            command = _cmd_line(call, executable, args)
        try:
            done = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as error:
            raise CallError(call, f"no answer in {timeout:.0f} s") from error
        if done.returncode != 0:
            lines = [
                line for line in (done.stderr or done.stdout).strip().splitlines() if line.strip()
            ]
            raise CallError(call, lines[-1] if lines else f"exit {done.returncode}")
        text = done.stdout.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError as error:
            raise CallError(call, "the answer is not JSON") from error

    return run


def _cmd_line(call: str, executable: str, args: list[str]) -> str:
    """The command line that runs a batch file with *args* as literal data.

    Every argument is wrapped in double quotes with each quote inside doubled:
    cmd.exe then sees every character of a value inside a quoted stretch, so
    ``& | < > ^ ( )`` are data, and the program behind the batch file (the C
    runtime's parser) reads ``""`` inside quotes as one quote. ``cmd /d /s /c``
    strips only the outer pair. What cmd.exe expands even inside quotes -- a
    ``%`` and a line break -- is refused rather than guessed at.
    """
    for arg in args:
        if any(char in arg for char in "%\r\n\x00"):
            raise CallError(
                call,
                f"refused {arg!r}: cmd.exe, which runs this CLI on Windows, would read a % or "
                "a line break in it as part of a command",
            )

    def quoted(value: str) -> str:
        # a run of backslashes before a quote is doubled for the C runtime
        escaped = re.sub(r'(\\*)"', lambda m: m.group(1) * 2 + '""', value)
        return '"' + re.sub(r"(\\+)$", r"\1\1", escaped) + '"'

    return f'cmd.exe /d /s /c "{" ".join(quoted(part) for part in (executable, *args))}"'


def tags(items: Any) -> dict[str, str]:
    """AWS's ``[{"Key": .., "Value": ..}]`` as the map Terraform writes."""
    if isinstance(items, dict):
        return {str(k): str(v) for k, v in items.items()}
    out: dict[str, str] = {}
    for item in items or []:
        if isinstance(item, dict) and "Key" in item:
            out[str(item["Key"])] = str(item.get("Value", ""))
    return out


def last_segment(value: Any) -> str | None:
    """``https://.../zones/us-central1-a`` -> ``us-central1-a``."""
    if not isinstance(value, str) or not value:
        return None
    return value.rstrip("/").rsplit("/", 1)[-1]
