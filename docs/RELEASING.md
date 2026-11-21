# Versions and releases

MediaForge uses [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

| Change | Bump | Example |
| --- | --- | --- |
| A bug fix, nothing new | PATCH | 0.2.0 to 0.2.1 |
| A new feature that does not break anything | MINOR | 0.2.1 to 0.3.0 |
| A change that breaks how people use it (renamed settings, removed formats) | MAJOR | 0.3.0 to 1.0.0 |

Below 1.0.0 means "still changing". 1.0.0 is the first release the project calls stable and complete; after that, new features are 1.1.0, 1.2.0 and so on, and fixes are 1.0.1.
"Version 1.1" and "ver 2.0" in everyday speech are the same idea: `1.1.0` and `2.0.0`.

## Releasing a version

1. Move the items under "Unreleased" in `CHANGELOG.md` into a new heading, for example `## [0.3.0]`.
2. Change `__version__` in `backend/app/__init__.py` to the same number.
3. Run `ruff check`, `ruff format --check` and `pytest` in `backend/`, and tick the checklist in
   [TESTING.md](TESTING.md).
4. Commit: `git commit -am "release: 0.3.0"`.
5. Tag the commit and push the tag:
   ```
   git tag -a v0.3.0 -m "MediaForge 0.3.0"
   git push origin main --tags
   ```
6. On GitHub, open **Releases**, choose **Draft a new release**, pick the tag `v0.3.0`, paste the
   changelog entry and publish. GitHub adds a source download automatically.

The running app shows its version at `/api/health`.

## Branches

Keep `main` working. Do new work on a branch such as `feature/proxy-setting`, merge it when the
tests pass, then release from `main`.
