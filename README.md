# MediaForge

A media converter that runs on your own machine. Paste a video URL or upload a local file, choose a format, and download the result as MP3, M4A, AAC, WAV, FLAC, OGG, Opus, MP4, WebM or MKV.

It uses only free, open-source tools: [FastAPI](https://fastapi.tiangolo.com/), [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [FFmpeg](https://ffmpeg.org/). No accounts, API keys or paid services.

![MediaForge screenshot](docs/screenshot.png)

## Features

- Convert from a video URL (any site supported by yt-dlp) or from an uploaded audio/video file.
- Audio formats: MP3, M4A, AAC, WAV, FLAC, OGG, Opus, with selectable bitrate for lossy formats.
- Video formats: MP4, WebM, MKV, with a maximum-resolution option (360p to 1080p, or best available).
- Preview the title, uploader and duration of a URL before converting.
- Convert a whole playlist: pick the videos you want, then save them to a folder on your computer, download a ZIP, or both.
- Title, artist, album and cover art are written into the files (MP3, M4A, FLAC, Ogg, Opus, MP4, MKV). Playlist items get the playlist name as album and their position as track number.
- Car presets for the Sony XAV-W650BT and similar older head units (see below).
- Configurable limits for video length and upload size.
- Temporary files are deleted after each download.
- Pasting a link shows the thumbnail, title, channel, length, views and date, and lists only the video qualities that video really has (4K, 1440p60, 1080p and so on). Nothing is upscaled.
- Download the thumbnail in any size the site offers, as JPG, PNG or WebP, optionally cropped to a square.
- Video without sound (any quality), and square cover art that car units and Windows can show on MP3 and M4A files.
- Works on phones and tablets too: see "Using it from other devices".
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

3. Start the server. From the project folder this works on every system:

   ```bash
   python run.py
   ```

   (Developers can also run `uvicorn app.main:app --reload` from the `backend` folder.)

4. Open <http://localhost:8000>.

To check that FFmpeg and the JavaScript runtime were found, open <http://localhost:8000/api/health>. It reports `"ffmpeg": true` and lists the detected runtimes under `js_runtimes`.

## Usage

1. Choose the **Link**, **File** or **Playlist** tab.
2. Enter a link (use **Preview** to check it first), choose a file, or paste a playlist link and select **Load playlist**.
3. Pick an output format and quality.
4. Select **Convert and download**. Long videos and large files can take a few minutes.

### Playlists

Paste a playlist link on the **Playlist** tab and select **Load playlist**. Untick any videos you do not want, choose where the files go, then start the job. Videos are converted one after another, and any that fail (private or removed videos, for example) are listed and skipped.

- **Save to a folder on this computer** puts the files in `downloads/<playlist name>` inside the project folder (change it with `MEDIAFORGE_DOWNLOAD_DIR`). Files are named `01 - Title.mp3` so they play in playlist order. Copy the folder to a USB stick.
- **Make a ZIP to download** builds a ZIP you can download when the job finishes.
- Both can be on at the same time.

### Video quality, 4K and 8K

When you paste a link, the Quality menu lists what that video offers, for example `2160p60 (4K)`, `1440p30 (2K)` and `1080p`, with an estimated size. A video that only has 720p will only list 720p. Above 1080p, YouTube provides VP9 or AV1 video instead of H.264, so **MKV or WebM** plays these most reliably. MP4 works too, but may not play on older devices. On the File and Playlist tabs the menu is a maximum ("Up to 1440p"), and each video is downloaded at the best quality it has up to that limit.

### Thumbnails, covers and sound

- **Download thumbnail** (under the video preview) saves the thumbnail in any size the site lists, as JPG, PNG or WebP, optionally cropped to a square.
- **MP3 and M4A** files get a square cover and the title, artist and album. If a cover cannot be added, the page says so after the download.
- **Remove the sound** (video formats) gives a silent video at the quality you picked.

### Using it from other devices

MediaForge runs on one computer, and any device with a browser can use it:

| Device | How |
| --- | --- |
| Windows, macOS, Linux | Install the requirements and run `python run.py`. |
| Android phone or tablet | Open it from the computer (below), or run it on the phone itself with [Termux](https://termux.dev/): `pkg install python ffmpeg`, then `pip install -r backend/requirements.txt` and `python run.py`. |
| iPhone and iPad | Open it from the computer (below). iOS cannot run the server itself. |

To use a phone or tablet with your computer, start the server with `python run.py --lan` and open the address it prints (for example `http://192.168.1.20:8000`) on a device on the same Wi-Fi. In your browser's menu, **Add to Home screen** (or **Install app**) puts it on the home screen like an app. Converted files download to the phone. A playlist's "save to a folder" option saves on the computer running MediaForge, and the Open folder button only works there.

`--lan` lets anyone on the network use MediaForge, and it has no sign-in. Use it on a network you trust, and never expose it to the internet.

### Older car head units (Sony XAV-W650BT)

This Sony unit cannot play the H.264 video that normal MP4 files use. According to Sony's manual it plays only:

| Container | Video | Audio | Limits |
| --- | --- | --- | --- |
| MP4 | MPEG-4 Simple Profile | AAC | 4 Mbps, 720 x 576, 30 fps |
| AVI | Xvid (MPEG-4 ASP) | MP3 | 8 Mbps, 720 x 576, 30 fps |

Choose **Video**, then **Sony car MP4** (about 3.3 Mbps video and 192 kbps AAC audio) or **Sony car AVI** (about 6.5 Mbps video and 192 kbps MP3 audio). Try the MP4 first and use the AVI if it will not play. Format the USB stick as FAT32. For music only, use MP3 at 192 kbps or lower, because Sony lists 48 to 192 kbps for MP3. The files are stereo. The unit's Dolby Digital decoding is for DVD discs, and its four speakers are fed from the stereo signal, so use the unit's own sound settings (EQ and fader) to shape it. These presets were checked with FFmpeg, not on a real head unit, and Sony says playback is not guaranteed.

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Server status, FFmpeg availability, detected JavaScript runtimes |
| GET | `/api/formats` | Supported formats, quality options and limits |
| POST | `/api/info` | Body `{"url": "..."}`. Returns title, duration, uploader, views, date, thumbnails, and the available video qualities |
| POST | `/api/thumbnail` | Body `{"url": "...", "id": "...", "format": "jpg", "square": false}`. Returns the thumbnail image |
| POST | `/api/convert` | Body `{"url": "...", "format": "mp3", "quality": "192", "mute": false}`. Video quality can be `best`, a height such as `2160`, or a height and frame-rate cap such as `1440@30`. Returns the converted file |
| POST | `/api/playlist/info` | Body `{"url": "..."}`. Lists the videos in a playlist |
| POST | `/api/jobs` | Starts a playlist job: `title`, `items` (`title`, `url`), `format`, `quality`, `save_to_folder`, `make_zip` |
| GET | `/api/jobs/{id}` | Progress of a job, with the state of each video |
| POST | `/api/jobs/{id}/cancel` | Stops after the current video |
| GET | `/api/jobs/{id}/zip` | Downloads the job's ZIP |
| POST | `/api/jobs/{id}/open-folder` | Opens the job's folder in the file manager |
| POST | `/api/convert-file` | Multipart form with `file`, `format`, optional `quality`. Returns the converted file |

Interactive API docs are available at <http://localhost:8000/docs> while the server is running.

Errors are returned as JSON, for example `{"detail": "Unsupported format 'exe'."}`.

## Configuration

Set these environment variables before starting the server (or in `docker-compose.yml`).

| Variable | Default | Meaning |
| --- | --- | --- |
| `MEDIAFORGE_MAX_DURATION` | `3600` | Longest video accepted from a URL, in seconds |
| `MEDIAFORGE_MAX_UPLOAD_MB` | `500` | Largest uploaded file, in megabytes |
| `MEDIAFORGE_DOWNLOAD_DIR` | `../downloads` | Where playlist folders are saved |
| `MEDIAFORGE_MAX_PLAYLIST_ITEMS` | `200` | Most videos accepted from one playlist |
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
│   │   ├── transcoder.py    # FFmpeg conversion for uploaded files and the car presets
│   │   ├── jobs.py          # background playlist jobs
│   │   ├── cover.py         # square cover art for MP3 and M4A
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
│   ├── app.js
│   ├── manifest.webmanifest # lets phones add it to the home screen
│   ├── icons/
│   ├── favicon.svg
│   └── fonts/           # Archivo variable font (SIL OFL)
├── run.py                   # starts the server (--lan for other devices)
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
