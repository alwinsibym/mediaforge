"""Print the CHANGELOG.md section for one version, for use as GitHub release notes.

    python scripts/release_notes.py v1.1.0
"""

import re
import sys
from pathlib import Path


def section(version: str, text: str) -> str:
    version = version.lstrip("v")
    pattern = rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)"
    match = re.search(pattern, text, re.S | re.M)
    if not match:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    return match.group(1).strip()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: release_notes.py v1.2.3")
    changelog = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    print(section(sys.argv[1], changelog.read_text(encoding="utf-8")))
