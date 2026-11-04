"""``infragram check:policy``: what a reviewer would stop in a diagram, and
what Checkov or Trivy find in a Terraform folder when one is installed.

A diagram -- a ``.infragram.json`` document, a diagram file, or a page or
picture that carries its document -- is read against the diagram rules
(:mod:`infragram.review.policy`); a folder is handed to the scanner. Findings are
reported and, unless ``--strict``, do not fail the command: a skeleton
Infragram writes is where the code starts, and a scanner flags much of it.
``--json`` prints the same as one JSON document (:func:`infragram.review.policy.policy_json`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    from pydantic import ValidationError

    from ...compose import ComposeError
    from ...exports import ExportError
    from ...review.policy import (
        RULES,
        SCANNERS,
        SourceReport,
        diagram_findings,
        policy_json,
        scan_folder,
        scanner_on_path,
    )
    from .diff import load_any

    parser = argparse.ArgumentParser(
        prog="infragram check:policy",
        description="Check a diagram against the policy rules (a database in a public subnet, "
        "the internet reaching a database or a private subnet, SSH, RDP or every port open "
        "to the internet), and a Terraform folder with Checkov or Trivy when installed.",
        epilog="rules: " + "; ".join(f"{rule}: {what}" for rule, what in RULES.items()),
    )
    parser.add_argument(
        "sources",
        nargs="+",
        type=Path,
        metavar="SOURCE",
        help="a document, a diagram file, a page or picture carrying its document, or a "
        "Terraform folder",
    )
    parser.add_argument(
        "--scanner",
        choices=("auto", *SCANNERS, "none"),
        default="auto",
        help="for a folder: the scanner to run (default auto: the first of "
        f"{', '.join(SCANNERS)} on the PATH; none: never)",
    )
    parser.add_argument(
        "--strict", action="store_true", help="fail (exit 1) when anything is found"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print what was read and found as one JSON document and nothing else on stdout: "
        "each source, every finding (rule, severity, message, the element or the scanner's "
        "resource, file and line) and the verdict; the exit status is the same",
    )
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)

    reports: list[SourceReport] = []
    for source in options.sources:
        if source.is_dir():
            scanner = None if options.scanner == "none" else scanner_on_path(options.scanner)
            if scanner is None:
                wanted = " or ".join(SCANNERS) if options.scanner == "auto" else options.scanner
                note = f"no scanner ({wanted} is not on the PATH); a folder is only read by one"
                reports.append(
                    SourceReport(path=str(source), kind="folder", status="skipped", note=note)
                )
                if not options.json:
                    print(f"SKIP     {source}: {note}")
                continue
            try:
                findings = scan_folder(source, scanner)
            except RuntimeError as error:
                print(f"ERROR: {source}: {error}", file=sys.stderr)
                return 2
            reports.append(
                SourceReport(
                    path=str(source),
                    kind="folder",
                    status="scanned",
                    scanner=scanner,
                    findings=findings,
                )
            )
            heading = f"SCANNED  {source} with {scanner}: {len(findings)} finding(s)"
        else:
            try:
                project = load_any(source)
            except (ExportError, ComposeError, ValidationError, ValueError, OSError) as error:
                print(f"ERROR: {error}", file=sys.stderr)
                return 2
            findings = diagram_findings(project)
            reports.append(
                SourceReport(path=str(source), kind="diagram", status="read", findings=findings)
            )
            heading = f"READ     {source}: {len(findings)} finding(s) against {len(RULES)} rules"
        if options.json:
            continue  # the JSON document says it all at the end
        print(heading)
        for finding in findings:
            print(
                f"POLICY   {finding.severity:<7} {finding.rule} {finding.where}: {finding.message}"
            )
    found = [finding for report in reports for finding in report.findings]
    if options.json:
        print(json.dumps(policy_json(reports, strict=options.strict), ensure_ascii=False, indent=2))
        return 1 if found and options.strict else 0
    if not found:
        print("OK       nothing found")
        return 0
    print(f"{'FAIL' if options.strict else 'WARN':8} {len(found)} finding(s)")
    return 1 if options.strict else 0
