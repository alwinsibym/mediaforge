# Testing checklist

A manual checklist to run before calling a version finished. MediaForge is a personal project
that runs on your own computer, so this covers how well it works, what it can and cannot do,
and where it breaks. Copy the file, tick the boxes and write your results in the blanks.

Test with content you own or that is licensed for copying (Creative Commons, public domain,
your own uploads).

Version tested: ________  Date: ________  Computer / internet speed: ________

## 1. Automatic checks

- [ ] `cd backend && python -m ruff check .` passes
- [ ] `python -m ruff format --check .` passes
- [ ] `python -m pytest -q` passes (all tests)
- [ ] `/api/health` shows the version, yt-dlp version, and `ffmpeg: true`
- [ ] Fresh install works from the README steps (new virtual environment, new folder)
- [ ] Docker: `docker compose up --build` starts and the page opens on `http://localhost:8000`

## 2. Usage: does each feature do what it says?

Audio
- [ ] Link to MP3 (192 kbps): plays, has title, artist, cover art
- [ ] Link to M4A, AAC, WAV, FLAC, OGG, Opus: each plays in a media player
- [ ] M4A and Opus are quick (no re-encoding): note the time ______ s
- [ ] Even out the volume on two songs of different loudness: they sound similar

Video
- [ ] MP4 at 1080p, 720p, 360p: resolution matches (check with the player's file info)
- [ ] WebM and MKV play
- [ ] "Video without sound" has no audio track
- [ ] Embed subtitles on a video that has them, and a video that has none (clear message)
- [ ] Skip sponsor segments on a YouTube video that has them

Edits
- [ ] Rename a single link: the file name and the title tag both match
- [ ] Rename an uploaded file
- [ ] Trim: start 0:10, end 0:30 gives about 20 s (check the length) ______ s
- [ ] Trim with an end before the start shows a clear message
- [ ] Split by chapter on a video with chapters gives one file per chapter in a ZIP

Files
- [ ] Upload an MP4 and convert to MP3
- [ ] Upload a file over the size limit: clear message
- [ ] Upload a text file renamed to `.mp3`: clear message, no crash

Playlists
- [ ] Load a 5-video playlist, deselect one, convert: 4 files, correct track numbers
- [ ] Album tag is the playlist name
- [ ] Save to folder, ZIP, and both
- [ ] Parallel downloads 1, 2 and 3: note the total time ______ / ______ / ______
- [ ] A private or deleted video in the playlist fails alone; the rest continue
- [ ] Retry brings the failed videos back and converts them

Controls and screens
- [ ] Cancel during a download stops it and leaves no temporary files
- [ ] History lists finished downloads; "Use again" fills the form
- [ ] Settings save and are still there after restarting
- [ ] Update yt-dlp works and shows the new version
- [ ] Light, Dark and System themes; choice survives a reload
- [ ] Sony presets: files play on the head unit (note which preset) ______

## 3. Failure handling

Each failure should show a title, an `MF-` code and an expandable explanation.

- [ ] Wrong link (`https://example.com/nothing`): MF-SITE-06 or similar
- [ ] Deleted or private video: MF-SITE-05
- [ ] Turn the internet off mid-download: download pauses, then resumes when it is back
- [ ] Turn the internet off, close MediaForge, reopen: the unfinished download is listed
- [ ] Rename ffmpeg temporarily (or remove it from PATH): MF-TOOL-01 with install steps
- [ ] Fill the disk quota or pick a read-only folder: a clear message, not a crash
- [ ] Very long video over the limit: MF-LIM-02
- [ ] Browser sign-in with Chrome open: MF-COOK-01 explains the problem; Firefox works

## 4. Speed and resources

Use the same 10-minute video each time and write the times.

| Test | Result |
| --- | --- |
| MP3 192 kbps, 10 min video | ______ s |
| M4A stream copy, same video | ______ s |
| MP4 1080p, same video | ______ s |
| 1080p with aria2c on / off | ______ s / ______ s |
| 20-song playlist, parallel 1 / 2 / 3 | ______ / ______ / ______ s |
| Peak memory while converting (Task Manager) | ______ MB |
| CPU while converting | ______ % |
| Idle memory when nothing runs | ______ MB |
| Temp folder size after a finished download | ______ MB (should be about 0) |

- [ ] Download speed is close to your line speed (compare with a speed test)
- [ ] A 100-video playlist finishes without the bot check, or waits and resumes
- [ ] Leave a long playlist running for 1 hour: no growing memory, no stuck jobs

## 5. Scope and limits

Note what is, and is not, covered. These are the facts to put in the README.

- [ ] Maximum video length (default 60 minutes): changed with `MEDIAFORGE_MAX_DURATION`
- [ ] Maximum upload size: changed with `MEDIAFORGE_MAX_UPLOAD_MB`
- [ ] Live streams are refused
- [ ] DRM-protected video (Netflix, Prime Video, Disney+) cannot be downloaded: expected
- [ ] Private videos need your own sign-in
- [ ] Only works while the computer running MediaForge is on and online
- [ ] Other devices on the network can use it only when you start it for them
- [ ] Settings, History and Unfinished downloads open only from the computer running it
- [ ] Nothing is sent anywhere except to the sites you download from

## 6. Site compatibility

Mark each site with what happens today. Sites change often, so repeat after a yt-dlp update.

| Site | Result | Notes |
| --- | --- | --- |
| YouTube (public video) | Works | Playlists may trigger the bot check; sign in through Firefox helps |
| YouTube (age-restricted) | ______ | Needs a browser sign-in |
| Instagram (reels) | Works | |
| X / Twitter (normal video) | Works | |
| X / Twitter (adult or sensitive video) | Fails: "no video could be found" | Needs a signed-in cookie from a browser (MF-SITE-04, MF-SITE-02) |
| Reddit | Fails: 403 | Needs a browser sign-in, an updated yt-dlp, and sometimes more (MF-SITE-03) |
| Facebook | ______ | |
| TikTok | ______ | |
| Vimeo | ______ | |
| SoundCloud | ______ | |
| Twitch (past broadcast / clip) | ______ | |
| Dailymotion | ______ | |
| A direct `.mp4` link | ______ | |

For every failure, copy the technical details from the error card into the notes.

## 7. Browsers and devices

- [ ] Chrome, Firefox, Edge on a computer
- [ ] A phone on the same Wi-Fi (start with `python run.py --lan`): page works, file downloads
- [ ] 375 px wide screen: no sideways scrolling
- [ ] Keyboard only: every button can be reached and has a visible focus
- [ ] Windows, and one other system if you have it (Linux, macOS)

## 8. Privacy and security

- [ ] Port is bound to `127.0.0.1` in Docker
- [ ] `cookies.txt` and `data/` are not in Git (`git status` is clean after using them)
- [ ] Another device cannot open Settings, History or the unfinished list
- [ ] Error messages do not show file paths from your computer, only technical details
- [ ] `pip list --outdated` and `pip-audit` checked for known problems

## 8b. Network and access

- [ ] `http://127.0.0.1/x` and `http://192.168.x.x/x` as a link: blocked with MF-SEC-01
- [ ] Start with `MEDIAFORGE_TOKEN=abc python run.py --lan`: a phone is asked for the token; this
      computer is not
- [ ] Wrong token is refused, right token is remembered after a reload
- [ ] Start 6 jobs quickly: the 6th is refused with MF-LIM-04
- [ ] Proxy field: a wrong proxy gives a clear network error, an empty one connects directly
- [ ] After `pip install curl_cffi`, "Imitate Chrome's connection" can be ticked; try Reddit again

## 9. Before a release

- [ ] CHANGELOG updated, `__version__` bumped
- [ ] README features and troubleshooting match what you saw above
- [ ] Screenshot is current
- [ ] Results of this checklist saved with the release notes
