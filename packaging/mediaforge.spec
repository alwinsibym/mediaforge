# PyInstaller recipe for the Windows app (also builds on Linux, which the tests use).
#   python packaging/build.py
# Do not call this file directly: build.py writes ytdlp_bundled.txt first.
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"

datas = [
    (str(ROOT / "frontend"), "frontend"),
    (str(BACKEND / "app" / "data"), "app/data"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "packaging" / "READ-ME-FIRST.txt"), "."),
    (str(ROOT / "packaging" / "ytdlp_bundled.txt"), "."),
]
binaries = []
hiddenimports = collect_submodules("app") + collect_submodules("uvicorn")

# yt-dlp and everything it loads by name at run time.
for package in ("yt_dlp", "yt_dlp_ejs", "mutagen", "Cryptodome", "websockets", "brotli", "certifi"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
    except Exception:
        continue
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# yt-dlp needs a JavaScript runtime for YouTube. The pip "deno" package carries the program.
try:
    import deno

    binaries.append((str(deno.find_deno_bin()), "."))
except Exception:
    pass

icon = ROOT / "frontend" / "icons" / "mediaforge.ico"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MediaForge",
    console=False,
    icon=str(icon) if icon.is_file() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="MediaForge")
