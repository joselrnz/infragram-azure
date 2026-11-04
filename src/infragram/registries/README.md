# registries/

The two places that turn on-disk JSON into validated in-memory objects.

| Module | Owns |
|---|---|
| `catalog.py` | provider skin catalog → `tuple[Provider, ...]` |
| `icons.py` | attribute access over an icon collection, grouped by service category |
| `naming.py` | how an icon id becomes a Python class name (the generated `nodes/`) |
| `manifests.py` | plugin manifest paths, semver rule, synchronized bump |

## catalog.py

`load_catalog(path)` parses `themes/catalog.json` and every provider
manifest it names, then fails loudly on anything suspect: unknown color role,
non-hex color, undeclared icon category, a `file` that escapes its directory,
a non-SVG extension, active content inside an SVG, or a sha256 that no longer
matches the bytes on disk. Nothing downstream re-checks these.

Icons may either ship inside the skin (`file`) or reference the shared vendor
library by id (`asset_ref`); both shapes converge on one validation path.

## manifests.py

`MANIFEST_PATHS` is the single source of truth for which plugin manifests
exist. `scripts/tools/bump-plugin-version.py` (the `infragram bump` command)
writes versions and `scripts/verify/plugin-package.py` gates them — both read
this list, so the bumper can never write a version the verifier does not
check. `pyproject.toml` carries the same version by hand. Adding a third
manifest is a one-line change here.
