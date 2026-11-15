# MediaForge

A media converter that runs on your own machine. Paste a video URL or upload a local file, choose a format, and download the result as MP3, M4A, AAC, WAV, FLAC, OGG, Opus, MP4, WebM or MKV.

It uses only free, open-source tools: [FastAPI](https://fastapi.tiangolo.com/), [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [FFmpeg](https://ffmpeg.org/). No accounts, API keys or paid services.

![MediaForge screenshot](docs/screenshot.png)

## Features

- Convert from a video URL (any site supported by yt-dlp) or from an uploaded audio/video file.
- Audio formats: MP3, M4A, AAC, WAV, FLAC, OGG, Opus, with selectable bitrate for lossy formats.
- Video formats: MP4, WebM, MKV, with a maximum-resolution option (360p to 1080p, or best available).
- Preview the title, uploader and duration of a URL before converting.
- Configurable limits for video length and upload size.
- Temporary files are deleted after each download.
- Light and dark theme, responsive layout.

## How it works

```
Browser (HTML/CSS/JS)  ->  FastAPI backend  ->  yt-dlp (download)  ->  FFmpeg (convert)
                                            ->  FFmpeg (uploaded files)
```

The backend serves the frontend and a small JSON/file API. For a URL, it downloads the media with yt-dlp and lets FFmpeg convert it. For an uploaded file, it runs FFmpeg directly. The converted file is streamed back and its temporary folder is removed.

## Requirements

- Python 3.10 or newer
- FFmpeg on your `PATH`
- A JavaScript runtime for YouTube (yt-dlp requires one). The Python requirements install [Deno](https://deno.com/) for you on most platforms. If your platform has no Deno package, install Node.js 20 or newer instead.

## Quick start with Docker

Docker bundles Python, FFmpeg and the JavaScript runtime, so nothing else needs installing.

```bash
git clone https://github.com/<your-username>/mediaforge.git
cd mediaforge
docker compose up --build
```

Open <http://localhost:8000>.

## Manual setup

1. Install FFmpeg.

   | System | Command |
   | --- | --- |
   | Windows | `winget install Gyan.FFmpeg` (then open a new terminal) |
   | macOS | `brew install ffmpeg` |
   | Debian/Ubuntu | `sudo apt install ffmpeg` |

2. Clone the repository and install the Python dependencies.

   Windows (PowerShell):

   ```powershell
   git clone https://github.com/<your-username>/mediaforge.git
   cd mediaforge\backend
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

   If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope Process Bypass` first.

   macOS / Linux:

   ```bash
   git clone https://github.com/<your-username>/mediaforge.git
   cd mediaforge/backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Start the server from the `backend` folder.

   ```bash
   uvicorn app.main:app --reload
   ```

4. Open <http://localhost:8000>.

To check that FFmpeg and the JavaScript runtime were found, open <http://localhost:8000/api/health>. It reports `"ffmpeg": true` and lists the detected runtimes under `js_runtimes`.

## Usage

1. Choose **From URL** or **From file**.
2. Enter a link (use **Preview** to check it first) or choose a file.
3. Pick an output format and quality.
4. Select **Convert and download**. Long videos and large files can take a few minutes.

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Server status, FFmpeg availability, detected JavaScript runtimes |
| GET | `/api/formats` | Supported formats, quality options and limits |
| POST | `/api/info` | Body `{"url": "..."}`. Returns title, duration, uploader, thumbnail |
| POST | `/api/convert` | Body `{"url": "...", "format": "mp3", "quality": "192"}`. Returns the converted file |
| POST | `/api/convert-file` | Multipart form with `file`, `format`, optional `quality`. Returns the converted file |

Interactive API docs are available at <http://localhost:8000/docs> while the server is running.

Errors are returned as JSON, for example `{"detail": "Unsupported format 'exe'."}`.

## Configuration

Set these environment variables before starting the server (or in `docker-compose.yml`).

| Variable | Default | Meaning |
| --- | --- | --- |
| `MEDIAFORGE_MAX_DURATION` | `3600` | Longest video accepted from a URL, in seconds |
| `MEDIAFORGE_MAX_UPLOAD_MB` | `500` | Largest uploaded file, in megabytes |
| `MEDIAFORGE_FRONTEND_DIR` | `../frontend` | Folder served as the web UI |
| `MEDIAFORGE_FFMPEG_DIR` | (auto-detect) | Folder containing `ffmpeg`, for when it is installed but not on the `PATH` |

## Development

```bash
cd backend
pip install -r requirements-dev.txt
ruff check .
pytest
```

The tests generate their own sample media with FFmpeg and mock the download step, so they need no network access. GitHub Actions runs the linter, the tests and a Docker build on every push.

## Project structure

```
mediaforge/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app and endpoints
│   │   ├── downloader.py    # yt-dlp download and conversion
│   │   ├── transcoder.py    # FFmpeg conversion for uploaded files
│   │   ├── ffmpeg_locator.py # finds FFmpeg even when the PATH is stale
│   │   ├── formats.py       # supported formats and quality options
│   │   ├── validators.py    # URL and filename validation
│   │   └── config.py        # settings and limits
│   ├── tests/
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── scripts/find-ffmpeg.ps1  # Windows helper: locate ffmpeg.exe
├── docs/screenshot.png
├── Dockerfile
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Troubleshooting

**"FFmpeg was not found on this computer", a red banner on the page, or `"ffmpeg": false` on the health page.** Merging video and audio (for example MP4 at 1080p) and converting formats need FFmpeg. MediaForge looks on the `PATH`, in the folder named by `MEDIAFORGE_FFMPEG_DIR`, and in the usual WinGet, Chocolatey and `C:\ffmpeg` locations. If it is installed but still not found, run `powershell -ExecutionPolicy Bypass -File scripts\find-ffmpeg.ps1` from the project folder. It finds `ffmpeg.exe` and prints the exact setting to use. Start MediaForge from the same terminal where you set it, or use `setx` and open a new terminal.

**YouTube downloads fail or report missing formats.** yt-dlp needs a JavaScript runtime. Check `js_runtimes` on the health page. If it is empty, install Deno (`pip install deno`) or Node.js 20+.

**Downloads that worked stop working.** Sites change often. Update yt-dlp with `pip install -U "yt-dlp[default]"` (or rebuild the Docker image with `docker compose build --no-cache`).

**"Sign in to confirm you're not a bot".** Some networks and IP addresses are challenged by YouTube. This is more common from cloud servers than from a home connection. Running MediaForge locally usually avoids it.

## Responsible use

MediaForge is for personal use with content you own, content under a licence that permits copying (such as Creative Commons), or other material you have the right to download. Many sites, including YouTube, restrict downloading in their terms of service, and copyright law applies. You are responsible for how you use this tool. It is designed to run locally and is not intended to be hosted as a public conversion service.

## Licence

MIT. See [LICENSE](LICENSE).
