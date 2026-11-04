"""What Terraform itself says of a configuration, without deploying it.

:func:`check_configuration` runs the Terraform CLI on a configuration's
folder, offline and without a cloud:

- ``terraform fmt -check``: the files ``fmt`` would lay out otherwise;
- ``terraform init -backend=false`` with the providers read from a plugin
  folder, and every registry module the configuration calls copied from the
  module cache into the folder and called there by path (:func:`vendor`),
  then ``terraform validate``;
- a plan against mocked providers: ``terraform test`` with a
  ``mock_provider`` for every provider the configuration or its modules use
  that could reach a cloud (all but :data:`LOCAL_PROVIDERS`), and a value
  made up for each variable nobody gave one, of the shape its name and type
  ask for (:func:`made_up`).

A mocked provider answers every read with made-up values and applies
nothing, so nothing is created, no cloud is called and no credentials are
read. ``infragram check:terraform`` runs it on a copy of a diagram's
skeletons or of a Terraform folder; the maintainer gate ``verify:terraform``
on every shipped template's skeletons.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from pydantic import Field

from ..iso3d.cache import cache_root
from .hclread import Expr, HclError, Type, evaluate, parse, type_of
from .mapping import load_modules
from .model import Record
from .readconfig import _allows, _version, module_cache

__all__ = [
    "LOCAL_PROVIDERS",
    "MOCKS_SINCE",
    "CheckError",
    "ConfigurationCheck",
    "Terraform",
    "Vendored",
    "check_configuration",
    "copy_configuration",
    "fetch",
    "made_up",
    "plugin_folder",
    "provider_source",
    "terraform_cli",
    "vendor",
]

#: Terraform's output as text whatever it prints (a plan's values are UTF-8, Windows' console is not).
TEXT: dict[str, Any] = {"text": True, "encoding": "utf-8", "errors": "replace"}
#: The first Terraform that plans against mocked providers (``mock_provider``).
MOCKS_SINCE = (1, 7)
#: Providers that work on the machine and reach nothing: every other provider a
#: configuration or its modules use is mocked for the plan. ``external`` (a
#: data source runs a program) and ``tls`` (``tls_certificate`` fetches a URL)
#: are mocked too: a checked folder runs nothing and reads nothing.
LOCAL_PROVIDERS = frozenset(
    {
        "hashicorp/archive",
        "hashicorp/cloudinit",
        "hashicorp/local",
        "hashicorp/null",
        "hashicorp/random",
        "hashicorp/time",
    }
)
#: What a copy leaves out: Terraform's working files and lock, state, and the
#: configuration's own tests (which may apply to a real cloud).
_LEAVE_OUT = (
    ".terraform",
    ".terraform.lock.hcl",
    "*.tfstate",
    "*.tfstate.*",
    "*.tftest.hcl",
    "*.tftest.json",
    ".git",
)
#: The files the check writes into the folder it checks.
TEST_FILE = "tests/infragram-check.tftest.hcl"
VALUES_FILE = "infragram-check.tfvars.json"
PROVIDERS_FILE = "infragram_check_providers.tf"
_REGISTRY_HOST = "registry.terraform.io"
#: A public registry module's source: ``namespace/name/provider``, and a submodule after ``//``.
_REGISTRY = re.compile(
    r"(?:registry\.terraform\.io/)?([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)"
    r"(?://(.+))?"
)
#: How long a run may hold the shared data folder before another takes it as left behind.
_STALE = 6 * 3600


class CheckError(RuntimeError):
    """The check cannot run: no Terraform CLI, or a download that failed."""


class ConfigurationCheck(Record):
    """What Terraform said of one configuration."""

    name: str
    #: The files ``terraform fmt`` would lay out otherwise.
    reformat: list[str] = Field(default_factory=list)
    #: What the plugin folder or the module cache lacks; nothing ran when anything does.
    missing: list[str] = Field(default_factory=list)
    #: The step Terraform refused (``fmt``, ``init``, ``validate``, ``plan``), and its last words.
    failed: str = ""
    message: str = ""
    validated: bool = False
    planned: bool = False
    #: Why a valid configuration was not planned: a provider the plan cannot mock.
    unplanned: str = ""
    #: What the plan would create, as ``Plan: N to add`` says.
    to_create: int | None = None
    #: The variables given a made-up value, and the providers the plan mocked.
    made_up: list[str] = Field(default_factory=list)
    mocked: list[str] = Field(default_factory=list)
    #: The plan, as ``terraform test -verbose`` prints it.
    plan_text: str = ""


class Terraform(Record):
    """The Terraform CLI a check runs, offline: the providers read from
    ``plugins``, what ``init`` installs kept in ``data``."""

    path: str
    version: tuple[int, ...]
    plugins: Path | None
    data: Path
    config: Path

    @property
    def mocks(self) -> bool:
        """Whether this Terraform plans against mocked providers."""
        return self.version[:2] >= MOCKS_SINCE

    def has(self, source: str) -> bool:
        """Whether the plugin folder holds the provider (any version)."""
        return self.plugins is not None and (self.plugins / _hosted(source)).is_dir()

    def run(self, arguments: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        # Offline: no CLI configuration (no mirror, no shared cache), no update
        # check, the providers from the plugin folder installed once into the
        # data folder the runs share.
        # The caller's TF_CLI_ARGS would add arguments to every step.
        env = {
            key: value
            for key, value in os.environ.items()
            if key != "TF_PLUGIN_CACHE_DIR" and not key.upper().startswith("TF_CLI_ARGS")
        }
        env.update(
            TF_CLI_CONFIG_FILE=str(self.config),
            TF_DATA_DIR=str(self.data),
            TF_IN_AUTOMATION="1",
            CHECKPOINT_DISABLE="1",
        )
        return subprocess.run(
            [self.path, *arguments], cwd=cwd, env=env, capture_output=True, **TEXT
        )


class Vendored(Record):
    """What :func:`vendor` found: every module folder the configuration uses,
    the root first, and the calls it could not point at a folder offline."""

    folders: list[Path] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


# ================================================================ the CLI
@contextlib.contextmanager
def terraform_cli(plugins: Path | None = None) -> Iterator[Terraform]:
    """The Terraform on PATH, reading providers from ``plugins`` (default
    :func:`plugin_folder`), for the length of the ``with``.

    What ``init`` installs is kept in Infragram's cache
    (``<cache>/terraform/data``), so a provider is copied there once for
    every run; a run that starts while another holds it gets a folder of its
    own, removed after.
    """
    path = shutil.which("terraform")
    if path is None:
        raise CheckError(
            "the Terraform CLI is not on PATH: https://developer.hashicorp.com/terraform/install"
        )
    base = cache_root() / "terraform"
    base.mkdir(parents=True, exist_ok=True)
    config = base / "empty.tfrc"
    config.write_text("", encoding="utf-8")
    lock = base / "data.lock"
    shared = _hold(lock)
    data = base / "data" if shared else Path(tempfile.mkdtemp(prefix="infragram-terraform-data-"))
    try:
        cli = Terraform(
            path=path,
            version=(0,),
            plugins=plugins if plugins is not None else plugin_folder(),
            data=data,
            config=config,
        )
        cli.version = _cli_version(cli)
        yield cli
    finally:
        if shared:
            lock.unlink(missing_ok=True)
        else:
            shutil.rmtree(data, ignore_errors=True)


def _hold(lock: Path) -> bool:
    """Whether this run takes the shared data folder: its lock is free, or
    was left by a run that ended long ago."""
    for _attempt in range(2):
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime < _STALE:
                    return False
                lock.unlink()
            except OSError:
                return False
    return False


def _cli_version(cli: Terraform) -> tuple[int, ...]:
    done = cli.run(["version", "-json"], Path.cwd())
    try:
        text = str(json.loads(done.stdout)["terraform_version"])
    except (ValueError, KeyError, TypeError):
        return (0,)
    return tuple(int(part) for part in re.findall(r"\d+", text.partition("-")[0])[:3]) or (0,)


def plugin_folder() -> Path | None:
    """Where the providers are read from: ``TF_PLUGIN_CACHE_DIR``, else the
    Terraform CLI configuration's ``plugin_cache_dir``, else Infragram's own
    ``<cache>/terraform/plugins`` (where :func:`fetch` puts them) when it
    exists."""
    configured = os.environ.get("TF_PLUGIN_CACHE_DIR") or _configured_cache()
    if configured:
        return Path(configured)
    own = cache_root() / "terraform" / "plugins"
    return own if own.is_dir() else None


def _configured_cache() -> str | None:
    """``plugin_cache_dir`` from the Terraform CLI configuration, when it names one."""
    named = os.environ.get("TF_CLI_CONFIG_FILE")
    if named:
        path = Path(named)
    elif os.name == "nt":
        path = (
            Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
            / "terraform.rc"
        )
    else:
        path = Path.home() / ".terraformrc"
    try:
        value = evaluate(
            parse(path.read_text(encoding="utf-8"), path.name).attributes["plugin_cache_dir"]
        )
    except (OSError, UnicodeDecodeError, HclError, KeyError):
        return None
    return (
        os.path.expandvars(os.path.expanduser(value)) if isinstance(value, str) and value else None
    )


def provider_source(text: str) -> str:
    """A provider's source as the check names it: lowercase, the public
    registry's host left out (``hashicorp/aws``)."""
    source = text.strip().lower().removeprefix(f"{_REGISTRY_HOST}/")
    return source if "/" in source else f"hashicorp/{source}"


def _hosted(source: str) -> Path:
    """Where a provider lives in a plugin folder: ``<host>/<namespace>/<type>``."""
    parts = source.split("/")
    return Path(*(parts if len(parts) == 3 else [_REGISTRY_HOST, *parts]))


def _tail(done: subprocess.CompletedProcess[str]) -> str:
    return "\n".join((done.stdout + done.stderr).strip().splitlines()[-25:])


def _long(path: Path) -> str:
    """A path Windows copies past 260 characters (registry modules' tests are deep)."""
    text = str(path.resolve())
    return "\\\\?\\" + text if os.name == "nt" and not text.startswith("\\\\?\\") else text


# ============================================================== downloads
def fetch(cli: Terraform, plugins: Path) -> list[str]:
    """Download the registry modules ``assets/terraform/modules.json`` pins,
    and the providers they and the clouds' skeletons need: the modules into
    the module cache (``<cache>/terraform/modules``, which the import reads
    too), the providers into ``plugins``. Network access; nothing is
    deployed. Returns what was fetched, ``namespace/name/provider version``."""
    table = load_modules()
    lines = ["terraform {", "  required_providers {"]
    lines += [
        f'    {key} = {{ source = "{p.source}", version = "{p.version}" }}'
        for key, p in table.providers.items()
    ]
    lines += ["  }", "}", ""]
    for key, module in table.modules.items():
        lines += [
            f'module "{key.replace("-", "_")}" {{',
            f'  source  = "{module.source}"',
            f'  version = "{module.version}"',
            "}",
            "",
        ]
    plugins.mkdir(parents=True, exist_ok=True)
    fetched: list[str] = []
    with tempfile.TemporaryDirectory(prefix="infragram-fetch-") as scratch:
        folder = Path(scratch)
        (folder / "main.tf").write_text("\n".join(lines), encoding="utf-8")
        env = dict(
            os.environ,
            TF_PLUGIN_CACHE_DIR=str(plugins),
            TF_IN_AUTOMATION="1",
            CHECKPOINT_DISABLE="1",
            # a module's own tests nest past Windows' path limit
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="core.longpaths",
            GIT_CONFIG_VALUE_0="true",
        )
        env.pop("TF_DATA_DIR", None)
        done = subprocess.run(
            [cli.path, "init", "-backend=false", "-input=false", "-no-color"],
            cwd=folder,
            env=env,
            capture_output=True,
            **TEXT,
        )
        if done.returncode:
            raise CheckError(f"terraform init could not fetch the modules\n{_tail(done)}")
        manifest = json.loads(
            (folder / ".terraform" / "modules" / "modules.json").read_text(encoding="utf-8")
        )
        for entry in manifest["Modules"]:
            source, version = str(entry.get("Source", "")), entry.get("Version")
            if not version or not source.startswith(f"{_REGISTRY_HOST}/"):
                continue
            address, _, subdir = source.removeprefix(f"{_REGISTRY_HOST}/").partition("//")
            target = module_cache().joinpath(*address.split("/")[:3], version)
            # a submodule's call (``ecs/aws//modules/cluster``) installs the whole package above it
            package = folder / entry["Dir"]
            for _ in Path(subdir).parts if subdir else ():
                package = package.parent
            if not target.is_dir():
                shutil.copytree(
                    _long(package),
                    _long(target),
                    ignore=shutil.ignore_patterns(".git", "test", ".github"),
                )
            fetched.append(f"{address} {version}")
    # one module two others call is fetched once
    return list(dict.fromkeys(fetched))


# =============================================================== the copy
def copy_configuration(source: Path, target: Path) -> Path:
    """A copy of a configuration's folder to check in, without Terraform's
    working files and lock, any state, or the configuration's own tests."""
    shutil.copytree(_long(source), _long(target), ignore=shutil.ignore_patterns(*_LEAVE_OUT))
    return target


def vendor(root: Path, original: Path | None = None) -> Vendored:
    """Point every module call of the configuration at ``root`` at a folder
    inside it, so ``terraform init`` reads every module offline: a registry
    module at a copy of the cached module under ``<root>/.vendor/`` (theirs
    too, a module that calls another), a local module outside ``root`` at a
    copy under ``<root>/.vendor/local/`` (``original`` is the folder
    ``root`` was copied from, which local paths are read against). Only what
    is called is followed, never a module's examples. What the module cache
    cannot answer, and a module from anywhere but the public registry, is
    named in ``missing``."""
    root = root.resolve()
    original = (original or root).resolve()
    #: every tree copied in, as (the folder read, its copy)
    trees: list[tuple[Path, Path]] = [(original, root)]
    found = Vendored()
    queue: list[tuple[Path, Path]] = [(root, original)]
    while queue:
        folder, read_from = queue.pop(0)
        folder = folder.resolve()
        if folder in found.folders or not folder.is_dir():
            continue
        found.folders.append(folder)
        for file in sorted(folder.glob("*.tf")):
            queue += _vendor_file(file, read_from, root, trees, found.missing)
    found.missing = list(dict.fromkeys(found.missing))
    return found


def _vendor_file(
    file: Path, read_from: Path, root: Path, trees: list[tuple[Path, Path]], missing: list[str]
) -> list[tuple[Path, Path]]:
    """Point one file's module calls into the copy; the folders they call,
    each with where it was read from."""
    text = file.read_text(encoding="utf-8")
    try:
        body = parse(text, file.name)
    except HclError:
        return []  # terraform init names what it cannot read
    lines = text.splitlines(keepends=True)
    called: list[tuple[Path, Path]] = []
    changed = False
    for block in body.blocks_of("module"):
        expr = block.body.attributes.get("source")
        source = evaluate(expr) if expr is not None else None
        if expr is None or not isinstance(source, str):
            continue
        if source.startswith(("./", "../")):
            wanted = (read_from / source).resolve()
            if not wanted.is_dir():
                continue  # terraform init says the module is missing, as it would anywhere
            copy = _copied(wanted, trees)
            if copy is None:
                # a module beside the configuration, not in it: copied in
                copy = root / ".vendor" / "local" / f"{len(trees)}-{wanted.name}"
                if not copy.is_dir():
                    shutil.copytree(
                        _long(wanted), _long(copy), ignore=shutil.ignore_patterns(*_LEAVE_OUT)
                    )
                trees.append((wanted, copy))
            if (file.parent / source).resolve() != copy.resolve():
                _point(lines, expr, source, _relative(copy, file.parent))
                changed = True
            called.append((copy, wanted))
            continue
        match = _REGISTRY.fullmatch(source)
        if match is None:
            missing.append(f"the module {source} (not from the public registry)")
            continue
        version_expr = block.body.attributes.get("version")
        constraint = evaluate(version_expr) if version_expr is not None else None
        constraint = constraint if isinstance(constraint, str) else None
        namespace, name, provider, inner = match.groups()
        base = module_cache() / namespace / name / provider
        versions = sorted(
            (v, entry.name)
            for entry in (base.iterdir() if base.is_dir() else ())
            if (v := _version(entry.name)) is not None
            and (constraint is None or _allows(constraint, v))
        )
        if not versions:
            missing.append(f"the module {namespace}/{name}/{provider} {constraint or ''}".strip())
            continue
        version = versions[-1][1]
        package = root / ".vendor" / namespace / name / provider / version
        if not package.is_dir():
            shutil.copytree(_long(base / version), _long(package))
        if (base / version, package) not in trees:
            trees.append((base / version, package))
        copy = package / inner if inner else package
        _point(lines, expr, source, _relative(copy, file.parent))
        if version_expr is not None:
            index = version_expr.line - 1
            rest = re.sub(r'\bversion\s*=\s*"[^"]*"', "", lines[index], count=1)
            lines[index] = rest if rest.strip() else ""
        changed = True
        called.append((copy, base / version / inner if inner else base / version))
    if changed:
        file.write_text("".join(lines), encoding="utf-8", newline="\n")
    return called


def _copied(path: Path, trees: list[tuple[Path, Path]]) -> Path | None:
    """Where ``path`` is in the copy: under the deepest tree read that holds it."""
    holding = [(read, copy) for read, copy in trees if path == read or read in path.parents]
    if not holding:
        return None
    read, copy = max(holding, key=lambda tree: len(tree[0].parts))
    return copy / path.relative_to(read)


def _point(lines: list[str], expr: Expr, old: str, new: str) -> None:
    index = expr.line - 1
    lines[index] = lines[index].replace(f'"{old}"', f'"{new}"', 1)


def _relative(target: Path, start: Path) -> str:
    """A local module source: a path from ``start`` that begins ``./`` or ``../``."""
    relative = os.path.relpath(target, start).replace(os.sep, "/")
    return relative if relative.startswith(("./", "../")) else "./" + relative


# ============================================================ providers
def _bodies(folder: Path) -> Iterator[Any]:
    for file in sorted(folder.glob("*.tf")):
        try:
            yield parse(file.read_text(encoding="utf-8"), file.name)
        except (HclError, OSError, UnicodeDecodeError):
            continue  # terraform names what it cannot read


def _uses(folder: Path) -> dict[str, str]:
    """The providers one module folder uses, local name -> source: those its
    ``required_providers`` declare, and those its resources, data sources and
    provider blocks name without declaring (``hashicorp/<name>``)."""
    declared: dict[str, str] = {}
    named: set[str] = set()
    for body in _bodies(folder):
        for block in body.blocks_of("terraform"):
            for inner in block.body.blocks_of("required_providers"):
                for name, expr in inner.body.attributes.items():
                    value = evaluate(expr)
                    source = value.get("source") if isinstance(value, dict) else None
                    declared[name] = provider_source(source if isinstance(source, str) else name)
        blocks = [
            *body.blocks,
            *(inner for check in body.blocks_of("check") for inner in check.body.blocks),
        ]
        for block in blocks:
            if block.type in ("resource", "data", "ephemeral") and block.labels:
                meta = block.body.attributes.get("provider")
                named.add(
                    meta.text.split(".")[0].strip()
                    if meta is not None
                    else block.labels[0].split("_")[0]
                )
            elif block.type == "provider" and block.labels:
                named.add(block.labels[0])
    named.discard("terraform")  # terraform_data and terraform_remote_state are built in
    uses = declared | {name: provider_source(name) for name in sorted(named - set(declared))}
    return {
        name: source
        for name, source in uses.items()
        if not source.startswith("terraform.io/builtin/")
    }


def _remote_states(folders: Sequence[Path]) -> list[str]:
    """The ``terraform_remote_state`` data sources a configuration reads:
    Terraform's own, which no mock answers, and which a plan reads from
    another configuration's backend."""
    return [
        f"data.terraform_remote_state.{block.labels[1]}"
        for folder in folders
        for body in _bodies(folder)
        for block in body.blocks_of("data")
        if len(block.labels) == 2 and block.labels[0] == "terraform_remote_state"
    ]


def _aliases(folder: Path) -> dict[str, list[str]]:
    """The root's aliased provider configurations: local name -> aliases."""
    aliases: dict[str, list[str]] = {}
    for body in _bodies(folder):
        for block in body.blocks_of("provider"):
            alias = block.body.attributes.get("alias")
            value = evaluate(alias) if alias is not None else None
            if block.labels and isinstance(value, str):
                aliases.setdefault(block.labels[0], []).append(value)
    return aliases


def _mocks(
    root: dict[str, str], modules: Sequence[dict[str, str]]
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """The providers the plan mocks, by the root's local name; those of them
    the root has to declare (only its modules use them); and those it cannot,
    a module's name for one the root gives to another provider."""
    mocked = {name: source for name, source in root.items() if source not in LOCAL_PROVIDERS}
    declare: dict[str, str] = {}
    clash: list[str] = []
    for uses in modules:
        for name, source in uses.items():
            if source in LOCAL_PROVIDERS or source in mocked.values():
                continue
            if name in root or name in mocked:
                clash.append(source)
                continue
            declare[name] = mocked[name] = source
    return mocked, declare, sorted(set(clash))


def _declare(folder: Path, providers: dict[str, str]) -> None:
    """Declare providers in the root, so the plan can mock them: in its
    ``required_providers`` block (a module has one), else in a file of
    their own."""
    entries = [f'    {name} = {{ source = "{source}" }}' for name, source in providers.items()]
    for file in sorted(folder.glob("*.tf")):
        text = file.read_text(encoding="utf-8")
        try:
            body = parse(text, file.name)
        except HclError:
            continue
        for block in body.blocks_of("terraform"):
            for inner in block.body.blocks_of("required_providers"):
                lines = text.splitlines(keepends=True)
                if not lines[inner.line - 1].rstrip().endswith("{"):
                    continue  # a one-line block: not one to add a line to
                lines[inner.line : inner.line] = [
                    f"{entry}  # infragram check:terraform, to mock it\n" for entry in entries
                ]
                file.write_text("".join(lines), encoding="utf-8", newline="\n")
                return
    lines = [
        "# Written by infragram check:terraform: the providers only the modules use,",
        "# declared in the root so the plan can mock them.",
        "terraform {",
        "  required_providers {",
        *entries,
        "  }",
        "}",
        "",
    ]
    (folder / PROVIDERS_FILE).write_text("\n".join(lines), encoding="utf-8")


# ============================================================ the values
_SUBSCRIPTION = "00000000-0000-0000-0000-000000000000"
_GROUP = f"/subscriptions/{_SUBSCRIPTION}/resourceGroups/rg-demo"
#: A public key of the shape the providers parse; its private half was never kept.
_SSH_KEY = (
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCo+Fce6o76FQNyHxq5Zbn1y0XIro8bqnzSPODLf9t1gKI2gPfYdnLD8+S2"
    "Add/FODfmAwivrx09xbmHiBUG29XBJf56bAxrBVj/RMso89k2SSj0tH87V0WNWUd/MlPYiD4i78cP1Xgq9AD947KLCSx32S5"
    "BBpqZzs4CDMmGrtbJobOIhQbp1xublNoVIkpbRPxjq5BJa0e2EM3APfu/Xw5RLol6UotBuef4PF5MHf3yNb6aUymHFouFSdt"
    "Tm9lfFqavezi79kMv3CQesVQ3dR3UdX7hVXJn9QQcjo+c5hKN1ZFy1hb4tI9Szx0IhWuEFpQB2hrMrQbuzDgcvt4q0rl"
    " infragram-plan-check"
)
#: A value for a variable nobody gave one, by its name: one of the shape the
#: providers and the registry modules check.
_VALUES: tuple[tuple[str, object], ...] = (
    (r"subscription_resource_id$", f"/subscriptions/{_SUBSCRIPTION}"),
    (r"public_key$|ssh_key", _SSH_KEY),
    (r"_ami$", "ami-0123456789abcdef0"),
    (
        r"resource_arn$",
        "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/demo/1",
    ),
    (r"_arn$", "arn:aws:iam::123456789012:role/demo"),
    (r"ip_address$", "203.0.113.10"),
    (r"domain_name$", "example.com"),
    (r"_domains$", ["example.com"]),
    (r"_package$", "lambda.zip"),
    (r"_service_name$", "com.amazonaws.us-east-1.s3"),
    (r"_location$", "EqDC2"),
    (r"bucket_name$", "demo-bucket-123456"),
    (r"_image$", "us-docker.pkg.dev/cloudrun/container/hello"),
    (r"target_resource_id$", f"{_GROUP}/providers/Microsoft.Storage/storageAccounts/demostorage"),
    (r"workspace_id$", f"{_GROUP}/providers/Microsoft.OperationalInsights/workspaces/law-demo"),
    (r"subresource_names$", ["blob"]),
    (
        r"assume_role_policy$",
        '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",'
        '"Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}',
    ),
    (
        r"identity_id$",
        f"{_GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-demo",
    ),
    (r"certificate_secret_id$", "https://kv-demo.vault.azure.net/secrets/tls"),
    (r"(password|secret)", "Demo-Passw0rd-123!"),
    (r"project_id$", "demo-project-123"),
    (r"subscription_id$|tenant_id$", _SUBSCRIPTION),
    (r"resource_group_name$", "rg-demo"),
    (r"resource_group_id$", _GROUP),
    (r"cidr_blocks?$|_cidrs?$", "10.9.0.0/16"),
    (r"policy_definition_id$", "/providers/Microsoft.Authorization/policyDefinitions/demo"),
    (r"service_provider_name$", "Equinix"),
    (r"peering_location$", "Silicon Valley"),
)
#: What a mocked data source gives where a random string would not pass, by provider.
_MOCK_DATA = {
    "hashicorp/aws": {
        "aws_availability_zones": '{ names = ["us-east-1a", "us-east-1b", "us-east-1c"], '
        'zone_ids = ["use1-az1", "use1-az2", "use1-az3"] }',
        "aws_caller_identity": '{ account_id = "123456789012", arn = "arn:aws:iam::123456789012:user/demo" }',
        "aws_partition": '{ partition = "aws", dns_suffix = "amazonaws.com" }',
        "aws_region": '{ name = "us-east-1", region = "us-east-1" }',
        "aws_iam_policy_document": '{ json = "{\\"Version\\":\\"2012-10-17\\",\\"Statement\\":[]}" }',
        "aws_vpc_endpoint_service": '{ service_name = "com.amazonaws.us-east-1.s3" }',
        "aws_iam_session_context": '{ issuer_arn = "arn:aws:iam::123456789012:role/demo", '
        'arn = "arn:aws:iam::123456789012:role/demo" }',
        "aws_iam_policy": '{ arn = "arn:aws:iam::aws:policy/demo" }',
        "aws_ami": '{ id = "ami-0123456789abcdef0" }',
    },
    "hashicorp/tls": {
        # the EKS module reads the OIDC issuer's certificate fingerprint
        "tls_certificate": '{ certificates = [{ sha1_fingerprint = "9e99a48a9960b14926bb7f3b02e22da2b0ab7280", '
        'is_ca = true, issuer = "CN=demo", subject = "CN=demo", serial_number = "1", '
        'signature_algorithm = "SHA256-RSA", public_key_algorithm = "RSA", '
        'not_before = "2026-01-01T00:00:00Z", not_after = "2036-01-01T00:00:00Z", '
        'version = 3, cert_pem = "" }] }',
    },
    "hashicorp/azurerm": {
        "azurerm_client_config": f'{{ tenant_id = "{_SUBSCRIPTION}", subscription_id = "{_SUBSCRIPTION}", '
        f'object_id = "{_SUBSCRIPTION}" }}',
    },
    "hashicorp/google": {
        # the Cloud SQL module picks a zone of the region when it is given none
        "google_compute_zones": '{ names = ["us-central1-a", "us-central1-b", "us-central1-c"] }',
    },
}


#: A variable holding address ranges, one a subnet (``public_subnet_cidrs``,
#: ``allowed_cidr_blocks``): a list of real ranges, never a list of one word.
_CIDR_LIST = r"cidrs$|cidr_blocks$"


def _cidr_list(name: str) -> list[str]:
    """Three distinct /24 ranges inside the ``10.9.0.0/16`` a network's range
    is made up as -- as many as the mocked region has zones, so a list read
    one a zone has an entry for each -- at a block the name picks, so the
    public and the private subnets' ranges do not overlap."""
    import zlib

    base = 4 * (zlib.crc32(name.encode("utf-8")) % 60 + 1)
    return [f"10.9.{base + i}.0/24" for i in range(3)]


def made_up(name: str, kind: Type = ("any",)) -> object:
    """A value for the variable ``name`` nobody gave one: of the shape its
    name asks for where a provider or module checks it (an ARN, a CIDR, an
    SSH public key...), else of its type (``"demo"``, ``1``, ``false``, a
    list of one, an empty map, an object of its required attributes). The
    name decides only where the type allows it: ``password_length`` is a
    number and ``enable_secret_rotation`` a bool, whatever their names say."""
    shape = kind[0]
    element = kind[1][0] if shape == "list" else None
    if re.search(_CIDR_LIST, name) and (
        shape == "any" or (shape == "list" and element in ("string", "any"))
    ):
        return _cidr_list(name)
    for pattern, value in _VALUES:
        if not re.search(pattern, name):
            continue
        if isinstance(value, list):
            if shape in ("list", "any"):
                return value
        elif shape in ("string", "any"):
            return value
        elif shape == "list" and element in ("string", "any"):
            return [value]
        break
    return _of_type(kind)


def _of_type(kind: Type) -> object:
    if kind[0] == "number":
        return 1
    if kind[0] == "bool":
        return False
    if kind[0] == "list":
        return [_of_type(kind[1])]
    if kind[0] == "map":
        return {}
    if kind[0] == "tuple":
        return [_of_type(item) for item in kind[1]]
    if kind[0] == "object":
        return {
            key: _of_type(inner)
            for key, (inner, optional, _default) in kind[1].items()
            if not optional
        }
    return "demo"


def _needed(folder: Path) -> dict[str, Type]:
    """The root's variables without a default, and their types."""
    return {
        block.labels[0]: type_of(block.body.attributes.get("type"))
        for body in _bodies(folder)
        for block in body.blocks_of("variable")
        if block.labels and "default" not in block.body.attributes
    }


def _given(folder: Path, var_files: Sequence[Path], variables: Sequence[str]) -> set[str]:
    """The variables something gives a value: the configuration's own
    ``terraform.tfvars`` and ``*.auto.tfvars`` files, and the files and
    values the caller names."""
    names = {item.partition("=")[0].strip() for item in variables}
    files = [
        folder / "terraform.tfvars",
        folder / "terraform.tfvars.json",
        *sorted(folder.glob("*.auto.tfvars")),
        *sorted(folder.glob("*.auto.tfvars.json")),
        *var_files,
    ]
    for file in files:
        try:
            text = Path(file).read_text(encoding="utf-8")
            if str(file).endswith(".json"):
                values = json.loads(text)
                names |= set(values) if isinstance(values, dict) else set()
            else:
                names |= set(parse(text, Path(file).name).attributes)
        except (OSError, UnicodeDecodeError, ValueError):
            continue  # terraform names what it cannot read
    return names


def _from_environment(needed: Sequence[str], given: set[str]) -> list[str]:
    """``NAME=VALUE`` for each variable only a ``TF_VAR_`` environment
    variable gives, to pass on as ``-var``: Windows hands a child process the
    environment with its names in capitals, and Terraform reads a variable's
    name as it is written. Nothing else gives these, so the order Terraform
    takes values in is kept."""
    return [
        f"{name}={os.environ[f'TF_VAR_{name}']}"
        for name in needed
        if name not in given and f"TF_VAR_{name}" in os.environ
    ]


def _test_file(mocked: dict[str, str], aliases: dict[str, list[str]]) -> str:
    lines = [
        "# Written by infragram check:terraform: a plan against mocked providers,",
        "# which create nothing and call no cloud.",
        "",
    ]
    for name, source in mocked.items():
        for alias in [None, *aliases.get(name, [])]:
            lines.append(f'mock_provider "{name}" {{')
            if alias:
                lines.append(f'  alias = "{alias}"')
            for data, defaults in _MOCK_DATA.get(source, {}).items():
                lines += [f'  mock_data "{data}" {{', f"    defaults = {defaults}", "  }"]
            lines += ["}", ""]
    lines += ['run "plan" {', "  command = plan", "}", ""]
    return "\n".join(lines)


# ============================================================== the check
def check_configuration(
    folder: Path,
    cli: Terraform,
    *,
    plan: bool = True,
    original: Path | None = None,
    var_files: Sequence[Path] = (),
    variables: Sequence[str] = (),
    name: str | None = None,
) -> ConfigurationCheck:
    """Run Terraform on the configuration in ``folder``: fmt, init and
    validate offline, then (``plan``) a plan against mocked providers.

    The check writes into ``folder`` (the modules it calls, the values it
    makes up, the mocked test), so check a copy of a folder you keep
    (:func:`copy_configuration`; ``original`` is where it was copied from).
    ``var_files`` and ``variables`` (``NAME=VALUE``) give the plan values as
    ``terraform plan`` takes them; a variable nothing gives a value gets a
    made-up one.
    """
    result = ConfigurationCheck(name=name or folder.name)
    fmt = cli.run(["fmt", "-check", "-recursive", "-list=true", "-no-color"], folder)
    listed = [line.strip().replace("\\", "/") for line in fmt.stdout.splitlines() if line.strip()]
    result.reformat = [path for path in listed if not path.startswith(".vendor/")]
    if fmt.returncode and not listed:
        result.failed, result.message = "fmt", _tail(fmt)
        return result
    vendored = vendor(folder, original)
    uses = [_uses(module) for module in vendored.folders]
    sources = sorted({source for used in uses for source in used.values()})
    result.missing = [
        *vendored.missing,
        *(f"the provider {source}" for source in sources if not cli.has(source)),
    ]
    if result.missing:
        return result
    mocked, declare, clash = _mocks(uses[0], uses[1:])
    if declare:
        _declare(folder, declare)
    folders = [f"-plugin-dir={cli.plugins}"] if cli.plugins is not None else []
    init = cli.run(["init", "-backend=false", "-input=false", "-no-color", *folders], folder)
    if init.returncode and "Access is denied" in init.stderr + init.stdout:
        # Windows: the provider the last configuration ran can still hold its
        # file a moment after Terraform exits, and the shared data folder
        # relinks it; once more, after it lets go
        time.sleep(3)
        init = cli.run(["init", "-backend=false", "-input=false", "-no-color", *folders], folder)
    if init.returncode:
        result.failed, result.message = "init", _tail(init)
        return result
    validate = cli.run(["validate", "-no-color"], folder)
    if validate.returncode:
        result.failed, result.message = "validate", _tail(validate)
        return result
    result.validated = True
    if not plan:
        return result
    if not cli.mocks:
        result.unplanned = (
            f"Terraform {'.'.join(map(str, cli.version))} cannot plan against mocked "
            f"providers; {'.'.join(map(str, MOCKS_SINCE))} and later can"
        )
        return result
    if clash:
        result.unplanned = (
            f"a module names {', '.join(clash)} as the root names another provider, "
            "so the plan could not mock it"
        )
        return result
    remote = _remote_states(vendored.folders)
    if remote:
        result.unplanned = (
            f"{', '.join(remote)} would read another configuration's state from its "
            "backend, which no mock answers"
        )
        return result
    needed = _needed(folder)
    given = _given(folder, var_files, variables)
    from_environment = _from_environment(list(needed), given)
    given |= {item.partition("=")[0] for item in from_environment}
    values = {name: made_up(name, kind) for name, kind in needed.items() if name not in given}
    result.made_up = sorted(values)
    (folder / VALUES_FILE).write_text(json.dumps(values, indent=2), encoding="utf-8")
    if "lambda.zip" in values.values() and not (folder / "lambda.zip").exists():
        with zipfile.ZipFile(folder / "lambda.zip", "w") as archive:
            archive.writestr("index.py", "def handler(event, context):\n    return {}\n")
    test = folder / TEST_FILE
    test.parent.mkdir(parents=True, exist_ok=True)
    test.write_text(_test_file(mocked, _aliases(folder)), encoding="utf-8")
    result.mocked = sorted(set(mocked.values()))
    done = cli.run(
        [
            "test",
            "-verbose",
            "-no-color",
            f"-var-file={VALUES_FILE}",
            *(f"-var-file={Path(file).resolve()}" for file in var_files),
            *(f"-var={item}" for item in [*variables, *from_environment]),
        ],
        folder,
    )
    result.plan_text = (done.stdout + done.stderr).strip()
    # a test file Terraform did not find would run no test at all, and still succeed
    if done.returncode or not re.search(r"\b1 passed, 0 failed\b", result.plan_text):
        result.failed, result.message = "plan", _tail(done)
        return result
    summary = re.search(r"Plan: (\d+) to add", result.plan_text)
    result.to_create = (
        int(summary.group(1)) if summary else (0 if "No changes." in result.plan_text else None)
    )
    result.planned = True
    return result
