"""Create a desktop shortcut that starts MediaForge and opens it in your browser.

    python scripts/create_shortcut.py              Desktop shortcut
    python scripts/create_shortcut.py --start-menu also a Start Menu entry (Windows)
    python scripts/create_shortcut.py --remove     delete the shortcut again

Run it with the same Python you use for MediaForge (activate the .venv first). Double-clicking
the shortcut starts the server without a console window, opens http://localhost:8000, and if
MediaForge is already running it only opens the page. Use Quit in the page to stop it.
Messages are written to data/mediaforge.log.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON_ICO = ROOT / "frontend" / "icons" / "mediaforge.ico"
ICON_PNG = ROOT / "frontend" / "icons" / "icon-512.png"
NAME = "MediaForge"


def windowless_python(executable: str) -> str:
    """pythonw.exe runs a script without a console window."""
    path = Path(executable)
    candidate = path.with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else str(path)


def powershell_script(lnk: Path, target: str, arguments: str, workdir: Path, icon: Path) -> str:
    """The PowerShell that creates a .lnk. Single quotes are doubled so odd paths survive."""

    def q(text: object) -> str:
        return "'" + str(text).replace("'", "''") + "'"

    return "\n".join(
        [
            "$shell = New-Object -ComObject WScript.Shell",
            f"$link = $shell.CreateShortcut({q(lnk)})",
            f"$link.TargetPath = {q(target)}",
            f"$link.Arguments = {q(arguments)}",
            f"$link.WorkingDirectory = {q(workdir)}",
            f"$link.IconLocation = {q(str(icon) + ',0')}",
            f"$link.Description = {q('Convert video links and files with MediaForge')}",
            "$link.Save()",
        ]
    )


def desktop_entry(python: str, run_py: Path, workdir: Path, icon: Path) -> str:
    """A freedesktop .desktop file (Linux)."""
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={NAME}",
            "Comment=Convert video links and files",
            f'Exec="{python}" "{run_py}" --open',
            f"Path={workdir}",
            f"Icon={icon}",
            "Terminal=false",
            "Categories=AudioVideo;",
            "",
        ]
    )


def windows_folder(special: str) -> Path:
    """Desktop or Start Menu folder, including OneDrive-redirected ones."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"[Environment]::GetFolderPath('{special}')"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())


def make_windows(args) -> list[Path]:
    python = windowless_python(sys.executable)
    folders = [windows_folder("Desktop")]
    if args.start_menu:
        folders.append(windows_folder("Programs"))
    made = []
    for folder in folders:
        lnk = folder / f"{NAME}.lnk"
        if args.remove:
            lnk.unlink(missing_ok=True)
            made.append(lnk)
            continue
        script = powershell_script(lnk, python, f'"{ROOT / "run.py"}" --open', ROOT, ICON_ICO)
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
        made.append(lnk)
    return made


def make_linux(args) -> list[Path]:
    home = Path(os.environ.get("HOME", "~")).expanduser()
    folders = [home / ".local" / "share" / "applications"]
    desktop = home / "Desktop"
    if desktop.is_dir():
        folders.append(desktop)
    made = []
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
        entry = folder / f"{NAME}.desktop"
        if args.remove:
            entry.unlink(missing_ok=True)
        else:
            entry.write_text(
                desktop_entry(sys.executable, ROOT / "run.py", ROOT, ICON_PNG), encoding="utf-8"
            )
            entry.chmod(0o755)
        made.append(entry)
    return made


def make_macos(args) -> list[Path]:
    path = Path.home() / "Desktop" / f"{NAME}.command"
    if args.remove:
        path.unlink(missing_ok=True)
    else:
        path.write_text(
            f'#!/bin/bash\n"{sys.executable}" "{ROOT / "run.py"}" --open\n', encoding="utf-8"
        )
        path.chmod(0o755)
    return [path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--start-menu", action="store_true", help="also add a Start Menu entry")
    parser.add_argument("--remove", action="store_true", help="remove the shortcut instead")
    args = parser.parse_args()

    if not args.remove:
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            print(
                "This Python does not have MediaForge's packages. Activate your .venv "
                "(or run pip install -r backend/requirements.txt) and run this again."
            )
            return 1

    if sys.platform == "win32":
        made = make_windows(args)
    elif sys.platform == "darwin":
        made = make_macos(args)
    else:
        made = make_linux(args)
    verb = "Removed" if args.remove else "Created"
    for path in made:
        print(f"{verb} {path}")
    if not args.remove:
        print("Double-click it to start MediaForge. Use Quit in the page to stop it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
