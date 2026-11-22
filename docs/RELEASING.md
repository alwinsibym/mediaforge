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
6. Pushing the tag publishes the GitHub release by itself (`.github/workflows/release.yml`), with the
   changelog section as the notes. For a tag made earlier, open **Actions**, choose **release**,
   click **Run workflow** and type the tag, for example `v0.1.0`.

Pushing the tag also builds the Windows app (`.github/workflows/windows-app.yml`), starts it as a check, and attaches `MediaForge-<version>-windows.zip` to the release. For a tag made earlier, run **windows-app** from the Actions tab and type the tag.

The running app shows its version at `/api/health`.

## The website

The website in `site/` is hosted on Vercel at https://mediaforge-zeta.vercel.app/ and is published automatically whenever `site/` changes on `main` (Vercel project settings: Root Directory `site`, Framework Preset Other, no build command). Its Download button asks GitHub for the newest release and links to that Windows zip, so a new release needs no change to the site. To rebuild the promo video, the share image or the screenshots after the app's look changes, run `python scripts/make_promo.py` and `python scripts/make_guide_images.py --site`, then commit the files in `site/`. Keep the address in `site/index.html`, `robots.txt`, `sitemap.xml`, `llms.txt` and `scripts/promo/end.html` the same if the site ever moves.

## Branches

Keep `main` working. Do new work on a branch such as `feature/proxy-setting`, merge it when the
tests pass, then release from `main`.
