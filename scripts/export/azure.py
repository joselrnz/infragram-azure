#!/usr/bin/env python3
"""Draw a live Azure subscription: read it through ``az``, export the picture.

Signs in as nothing itself. Whatever ``az login`` holds -- a user, a service
principal, a managed identity -- is what reads the estate, through Azure
Resource Graph, with that identity's own permissions. With no subscription
named, the one ``az account show`` reports is drawn.

    infragram export:azure                                  # current subscription, network view
    infragram export:azure --subscription "Prod" --view both --formats template,html,svg,png
    infragram export:azure --all-subscriptions --resource-group "rg-hub-*"
    infragram export:azure --list-subscriptions
    infragram export:azure --snapshot-out prod.json         # keep what was read ...
    infragram export:azure --from-snapshot prod.json        # ... and redraw it offline
    infragram export:azure --refresh prod-network.infragram.json --since prod.json  # read again

Exit status: 0 drawn; 1 the export failed --verify; 2 an option, a file or the
export was wrong; 3 az failed. With --refresh: 4 drawn, and something changed
since the earlier read (0 means nothing did), so a scheduled job can tell.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

# In a checkout the package is imported from src/; an installed wheel carries
# this script beside the package, which is already importable.
ROOT = next(
    (path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir()), None
)
if ROOT is not None:
    sys.path.insert(0, str(ROOT / "src"))

from infragram import compose  # noqa: E402
from infragram.cli.user.checker import checker  # noqa: E402
from infragram.cli.user.diff import load_any  # noqa: E402
from infragram.cli.user.export_project import price_for_export  # noqa: E402
from infragram.cli.user.options import (  # noqa: E402
    add_export_options,
    apply_render_settings,
    export_keywords,
    with_overrides,
)
from infragram.discovery import (  # noqa: E402
    VIEWS,
    AzureCliError,
    AzureSession,
    ImportOptions,
    blueprint,
    load_snapshot,
    save_snapshot,
)
from infragram.discovery.refresh import carry_layout, compare, mark  # noqa: E402
from infragram.exports import ExportError  # noqa: E402
from infragram.exports.written import blocking  # noqa: E402
from infragram.patterns import PatternError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infragram export:azure",
        description="Read an Azure subscription through the Azure CLI and export it as a diagram.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        conflict_handler="resolve",
    )
    add_export_options(parser, libraries="project", display="icon", title=False)
    parser.set_defaults(formats="template,html,svg,png", write_looks="both")
    source = parser.add_argument_group("what to read")
    source.add_argument(
        "--subscription",
        "-s",
        action="append",
        default=[],
        metavar="NAME_OR_ID",
        help="subscription to draw, by name or id; repeat for several "
        "(default: the current `az account show` subscription)",
    )
    source.add_argument(
        "--all-subscriptions",
        action="store_true",
        help="draw every enabled subscription the signed-in identity can see",
    )
    source.add_argument(
        "--management-group",
        "-m",
        action="append",
        default=[],
        metavar="NAME",
        help="draw every enabled subscription under this management group, at any depth; "
        "repeatable",
    )
    source.add_argument(
        "--resource-group",
        "-g",
        action="append",
        default=[],
        metavar="PATTERN",
        help="only resource groups matching this name pattern (* and ? allowed); repeatable",
    )
    source.add_argument(
        "--exclude-type",
        action="append",
        default=[],
        metavar="PATTERN",
        help="leave out resource types matching this pattern, e.g. 'microsoft.insights/*'",
    )
    source.add_argument(
        "--from-snapshot",
        type=Path,
        metavar="FILE",
        help="draw a snapshot saved earlier instead of calling Azure",
    )
    source.add_argument(
        "--snapshot-out",
        type=Path,
        metavar="FILE",
        help="also save what was read, to redraw later with --from-snapshot",
    )
    source.add_argument(
        "--no-changes",
        dest="changes",
        action="store_false",
        help="skip the last 14 days of changes (read by default)",
    )
    source.add_argument(
        "--no-findings",
        dest="findings",
        action="store_false",
        help="skip Defender for Cloud recommendations and Azure Policy results (read by default)",
    )
    source.add_argument(
        "--list-subscriptions",
        action="store_true",
        help="print the subscriptions az can see and exit",
    )

    again = parser.add_argument_group("reading it again")
    again.add_argument(
        "--refresh",
        type=Path,
        metavar="DIAGRAM",
        help="redraw this earlier export:azure diagram (a .infragram.json, or a page or picture "
        "that carries one; never a .py file, which would run) from the new read: what the "
        "reader moved or restyled keeps its "
        "place, what is new is laid out, and what changed is marked; exits 4 when something did",
    )
    again.add_argument(
        "--since",
        type=Path,
        metavar="SNAPSHOT",
        help="the snapshot the earlier diagram was drawn from, so --refresh can say what "
        "changed and not only what was added or removed; its subscriptions are read again "
        "when none is named",
    )

    drawing = parser.add_argument_group("how to draw it")
    drawing.add_argument(
        "--view",
        choices=(*VIEWS, "both"),
        default="network",
        help="network: VNets and subnets with resources placed in them (default); "
        "groups: resource groups only; both: export one of each",
    )
    drawing.add_argument(
        "--all",
        dest="everything",
        action="store_true",
        help="also draw plumbing (NICs, disks, public IPs, alert rules, extensions) "
        "and resource groups other services manage (AKS MC_*, Databricks)",
    )
    drawing.add_argument(
        "--references",
        action="store_true",
        help="also wire resources to what their properties name (web app to plan, "
        "cluster to workspace); off by default because they cross the picture",
    )
    drawing.add_argument(
        "--slug", help="file name for the exports (default: azure-<subscription>-<view>)"
    )
    drawing.add_argument("--title", help="diagram title")

    return parser


def verify_outputs(result) -> bool:
    """Check every exported document or picture using the packaged checker."""
    clean = True
    for label in ("template", "html", "svg", "png", "svg_icons", "png_icons", "drawio"):
        path = getattr(result, label, None)
        if path is None:
            continue
        # draw.io is checked by its exporter; the diagram checker reads our
        # document, HTML and SVG formats, plus carried PNG documents.
        if label == "drawio":
            continue
        good, message = checker().check_path(path)
        print(f"{'PASS' if good else 'FAIL'}     {message}")
        clean = good and clean
    return clean


def list_subscriptions(session: AzureSession) -> int:
    current = session.current_subscription()["id"]
    for entry in sorted(session.subscriptions(), key=lambda e: e["name"].lower()):
        mark = "*" if entry["id"] == current else " "
        tenant = entry["tenantName"] or entry["tenantId"]
        print(f"{mark} {entry['name']:<36} {entry['id']}  {entry['state']:<9} {tenant}")
    return 0


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    formats = tuple(part.strip() for part in options.formats.split(",") if part.strip())
    views = VIEWS if options.view == "both" else (options.view,)
    if options.view == "both" and options.slug:
        print("NOTE     --view both appends -network and -groups to --slug", file=sys.stderr)
    try:
        apply_render_settings(options)
        # refuse before reading Azure, not after: the read can take minutes
        if options.snapshot_out and not options.force and blocking([options.snapshot_out]):
            raise ValueError(
                f"refusing to overwrite {options.snapshot_out}: this tool did not write it, "
                "or it was edited since (pass --force to replace it)"
            )
        # the earlier diagram is read, never run: a .py diagram file is a
        # program, so it is composed on purpose first, not handed in here
        if options.refresh and options.refresh.suffix.casefold() == ".py":
            raise ValueError(
                f"--refresh reads a document, page or picture, not a diagram file that would run: "
                f"compose {options.refresh.name} first and refresh what it wrote"
            )
        previous = load_any(options.refresh) if options.refresh else None
        earlier = load_snapshot(options.since) if options.since else None
        if previous is not None and options.view == "both":
            raise ValueError("--refresh redraws one diagram: give its --view, network or groups")
        if earlier is not None and previous is None:
            raise ValueError("--since names the read an earlier diagram came from: add --refresh")
        if options.from_snapshot:
            snapshot = load_snapshot(options.from_snapshot)
        else:
            session = AzureSession()
            if options.list_subscriptions:
                return list_subscriptions(session)
            chosen = (
                session.under_management_groups(options.management_group)
                if options.management_group
                else []
            )
            again = (
                [entry["id"] for entry in earlier.get("subscriptions") or []]
                if earlier is not None
                and not (options.subscription or options.all_subscriptions or chosen)
                else []
            )
            if options.subscription or options.all_subscriptions or again or not chosen:
                chosen += [
                    entry
                    for entry in session.resolve(
                        options.subscription or again, every=options.all_subscriptions
                    )
                    if entry["id"] not in {c["id"] for c in chosen}
                ]
            print(
                f"READING  {', '.join(entry['name'] for entry in chosen)} through Azure Resource Graph",
                file=sys.stderr,
            )
            snapshot = session.snapshot(chosen, changes=options.changes, findings=options.findings)
        if options.snapshot_out:
            saved = save_snapshot(snapshot, options.snapshot_out, force=options.force)
            print(f"SNAPSHOT {saved}")

        clean = True
        changed = False
        for view in views:
            settings = ImportOptions(
                view=view,
                everything=options.everything,
                managed_groups=options.everything,
                references=options.references,
                resource_groups=tuple(options.resource_group),
                exclude_types=tuple(options.exclude_type),
                display="icon" if options.display == "icon" else "card",
            )
            slug = f"{options.slug}-{view}" if options.slug and len(views) > 1 else options.slug
            if previous is not None and not slug:
                slug = previous.slug
            plan, summary = blueprint(
                snapshot, settings, slug=slug, title=options.title, theme=options.theme
            )
            project = plan.to_project()
            if previous is not None:
                kept = carry_layout(previous, project)
                refresh = compare(snapshot, earlier=earlier, previous=previous, project=project)
                mark(project, refresh)
                changed = changed or refresh.any
                print(
                    f"REFRESH  {project.slug} · {kept} element(s) kept where the reader left them"
                )
                for line in refresh.lines():
                    print(f"         {line}")
            project = with_overrides(project, options)
            price_notes = price_for_export(project, options)
            drawn = formats
            if not summary.resources and not summary.networks:
                # an empty subscription or resource group has no picture to
                # draw; its page still shows the frames that were read
                drawn = tuple(f for f in formats if f not in ("svg", "png"))
                if drawn != formats:
                    print(
                        f"NOTE     {view} view: no resources to draw, so no SVG or PNG",
                        file=sys.stderr,
                    )
            result = compose.export(
                project,
                options.output_dir,
                formats=drawn,
                overwrite=options.force,
                **export_keywords(options),
            )
            print(
                f"PROJECT  {project.slug} · {view} view · "
                f"{len(project.topology.index()) - 1} elements"
            )
            for line in summary.lines():
                print(f"         {line}")
            for label in (
                "template",
                "html",
                "svg",
                "png",
                "svg_icons",
                "png_icons",
                "drawio",
                "terraform",
                "terraform_modules",
            ):
                path = getattr(result, label)
                if path is not None:
                    size = f" ({path.stat().st_size} bytes)" if path.is_file() else ""
                    print(f"{label.upper():8} {path}{size}")
            for note in (*price_notes, *result.notes):
                print(f"NOTE     {note}", file=sys.stderr)
            if options.verify:
                clean = verify_outputs(result) and clean
    except AzureCliError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 3
    except (
        ExportError,
        OSError,
        ValidationError,
        compose.ComposeError,
        PatternError,
        ValueError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if not clean:
        print("ERROR: the export did not pass verification", file=sys.stderr)
        return 1
    return 4 if changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
