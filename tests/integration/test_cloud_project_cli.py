from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())


def template_payload() -> dict:
    return {
        "schema_version": 1,
        "slug": "cli-cloud",
        "title": "CLI Cloud",
        "description": "A client connects to a cloud service.",
        "provider": "azure",
        "topology": {
            "id": "root",
            "name": "CLI Cloud",
            "type": "group",
            "children": [
                {
                    "id": "client",
                    "name": "Client",
                    "type": "client",
                    "connections": [{"target": "service", "label": "HTTPS"}],
                },
                {"id": "service", "name": "Service", "type": "service"},
            ],
        },
    }


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "infragram", *args],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_export_project_cli_writes_html_and_svg(tmp_path: Path) -> None:
    source = tmp_path / "source.infragram.json"
    source.write_text(json.dumps(template_payload()), encoding="utf-8")
    output = tmp_path / "dist"

    result = run_cli(
        "export:project",
        str(source),
        "--formats",
        "template,html,svg",
        "--renderer",
        "static",
        "--output-dir",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    assert (output / "cli-cloud.infragram.json").is_file()
    assert (output / "cli-cloud.html").is_file()
    assert (output / "cli-cloud.svg").is_file()
    assert "HTML" in result.stdout
    assert "SVG" in result.stdout


def test_export_project_cli_reports_validation_errors_without_tracebacks(tmp_path: Path) -> None:
    source = tmp_path / "bad.infragram.json"
    payload = template_payload()
    payload["provider"] = "unknown"
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = run_cli("export:project", str(source), "--output-dir", str(tmp_path / "dist"))

    assert result.returncode == 2
    assert "ERROR:" in result.stderr
    assert "unsupported cloud provider" in result.stderr
    assert "Traceback" not in result.stderr


def test_export_project_cli_refuses_edited_artifacts_without_force(tmp_path: Path) -> None:
    source = tmp_path / "source.infragram.json"
    source.write_text(json.dumps(template_payload()), encoding="utf-8")
    output = tmp_path / "dist"

    first = run_cli("export:project", str(source), "--formats", "html", "--output-dir", str(output))
    second = run_cli(
        "export:project", str(source), "--formats", "html", "--output-dir", str(output)
    )

    assert first.returncode == 0
    assert second.returncode == 0, second.stdout + second.stderr
    artifact = output / "cli-cloud.html"
    original = artifact.read_bytes()
    artifact.write_bytes(original + b"<!-- user edit -->")

    refused = run_cli(
        "export:project", str(source), "--formats", "html", "--output-dir", str(output)
    )
    assert refused.returncode == 2
    assert "refusing to overwrite" in refused.stderr
    assert artifact.read_bytes() == original + b"<!-- user edit -->"

    replaced = run_cli(
        "export:project", str(source), "--formats", "html", "--output-dir", str(output), "--force"
    )
    assert replaced.returncode == 0, replaced.stdout + replaced.stderr
    assert artifact.read_bytes() == original


def test_export_project_cli_runs_from_any_directory(tmp_path: Path) -> None:
    # A user exports a diagram from their own project folder: relative paths
    # resolve there, and only the plugin's src has to be on the Python path.
    workdir = tmp_path / "someone-elses-project"
    workdir.mkdir()
    (workdir / "site.infragram.json").write_text(json.dumps(template_payload()), encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "infragram",
            "export:project",
            "site.infragram.json",
            "--formats",
            "template,html",
            "--output-dir",
            "out",
        ],
        cwd=workdir,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (workdir / "out" / "cli-cloud.html").is_file()
    assert (workdir / "out" / "cli-cloud.infragram.json").is_file()
    checker = subprocess.run(
        [
            sys.executable,
            str(ROOT / "skills/infragram-azure/scripts/project_check.py"),
            "out/cli-cloud.html",
        ],
        cwd=workdir,
        text=True,
        capture_output=True,
        check=False,
    )
    assert checker.returncode == 0, checker.stdout + checker.stderr


if __name__ == "__main__":
    # `python tests/integration/test_cloud_project_cli.py` runs the suite too,
    # so the standalone CI step and `verify:all` exercise the CLI for real.
    import pytest

    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
