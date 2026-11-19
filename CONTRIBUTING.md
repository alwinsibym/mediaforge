# Contributing

MediaForge is a personal learning project, but fixes and ideas are welcome.

## Set up

```
git clone https://github.com/alwinsibym/mediaforge.git
cd mediaforge/backend
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
```

FFmpeg must be installed (see the README).

## Before you open a pull request

Run these in `backend/`:

```
ruff check .
ruff format --check .
pytest -q --cov=app
```

- Add or update a test for what you change. Tests never download from the internet: fake yt-dlp
  and FFmpeg calls, as the existing tests do.
- Keep error messages in plain English. New failures need an entry in `app/errors.py` with a
  code, a short summary, what happened, why, and what to do.
- Do not commit cookies, downloaded media or the `data/` folder.

## Branches and releases

Work on a branch such as `feature/proxy-setting`, keep `main` working, and describe the change
in `CHANGELOG.md`. Version numbers and the release steps are in
[docs/RELEASING.md](docs/RELEASING.md).

## Scope

MediaForge runs on your own computer for content you may copy. Features that turn it into a
public hosted service, or that bypass DRM or paywalls, will not be accepted.
