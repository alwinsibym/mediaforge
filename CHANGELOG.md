# Changelog

All notable changes to MediaForge are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

## [Unreleased]

### Added
- Tweaks on the File tab: video codec (H.264, H.265, VP9, AV1), resize 360p to 4K, compress to a target size, volume, fades and sound effects, replace or remove the sound, soft or burned-in subtitles, GIF or animated WebP, start and stop, remove hidden details, and a file info panel. New `/api/probe`; `/api/jobs/upload` takes `options`, `audio_file` and `subtitle_file`.
- A desktop shortcut (`scripts/create_shortcut.py`) using the MediaForge logo as its icon. It starts the server without a console window, opens the browser, and reuses a copy that is already running.
- `python run.py --open`, a Quit button in the page, and a log file at `data/mediaforge.log`.

## [0.3.0]

### Changed
- The page code is split from one `app.js` into ES modules in `frontend/js/`, checked by a browser smoke test (`scripts/ui_smoke.py`) and ESLint, both run in CI.

### Added
- Settings: a proxy field and "imitate Chrome's connection" (needs `curl_cffi`).
- Links to private addresses (127.0.0.1, 192.168.x.x, localhost) are blocked, with an override.
- Optional access token (`MEDIAFORGE_TOKEN`) for use with `--lan`.
- A limit on jobs waiting or running at once.
- Error codes MF-NET-04 (certificates), MF-SEC-01, MF-AUTH-01 and MF-LIM-04.
- `scripts/selftest.py` (every format on generated media) and `scripts/check_sites.py` (a site report).
- `MF-SITE-09` for sites that block your network address, such as Reddit's "Your IP address is unable to access the Reddit API".
- Test coverage reporting in CI, CI and licence badges, and `CONTRIBUTING.md`.

## [0.2.0]

### Added
- Live progress with percent, speed, time left and a Cancel button.
- System, Light and Dark theme.
- Faster downloads: stream copy for M4A and Opus, parallel playlist downloads (1 to 3),
  parallel fragments and optional aria2c.
- More options: even out the volume, skip sponsor segments, embed subtitles, trim a video,
  split by chapter.
- Settings: sign in through a browser's cookies or a `cookies.txt`, parallel downloads, aria2c,
  and a button that updates yt-dlp.
- History with "Use again", and a Retry button for failed playlist videos.
- Waiting and resuming when YouTube asks for a bot check or the internet drops, and a list of
  unfinished downloads to resume.
- Error messages with a plain-English title, an error code (`MF-...`) and an expandable
  explanation of what happened, why and what to do.
- Edit the file name and title of a single link or uploaded file before converting.

### Changed
- Clearer explanations for DNS, timeout, connection-reset, cookie and 403 failures.
- Docker publishes the port on `127.0.0.1` only.

### Fixed
- Windows text-decoding crash that hid cover art and printed a false warning.
- aria2c failing on networks without IPv6.

## [0.1.0]

First version: convert a link or a local file to MP3, M4A, AAC, WAV, FLAC, OGG, Opus, MP4,
WebM or MKV, playlists, metadata and cover art, and Sony car presets.
