## What does this PR do?

<!-- One or two sentences: what changed and why. -->

## Validation gates

<!-- Mark what you ran and that it passed. CI runs all of these on the PR too. -->

- [ ] `infragram verify:all`
- [ ] `python -m pytest tests/unit tests/skill`
- [ ] `INFRAGRAM_RUN_BROWSER_TESTS=1 python -m pytest tests/integration` (editor or export changes)
- [ ] Every shipped template still exports and passes `skills/infragram-azure/scripts/project_check.py`
- [ ] `infragram gen:nodes --check` and `infragram build:index` are clean (library or catalog changes)
- [ ] Plugin version bumped with `infragram bump` (user-visible changes)
- [ ] Docs updated in the same PR where behavior changed

## Checklist

- [ ] No provider-specific branch added to the editor shell or runtime; library knowledge lives in catalogs, themes, and frame data
- [ ] New artwork has source, release, terms URL, and SHA-256 in its pack catalog and an entry in `THIRD_PARTY_LICENSES.md`
- [ ] One project document remains the authority for every export; no format-specific layout
- [ ] Code of Conduct respected

## Related issues

<!-- Link any issues this closes, e.g. "Closes #12". -->
