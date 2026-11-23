"""MediaForge backend package."""

__version__ = "1.5.1"

from . import paths as _paths  # noqa: E402

# In the Windows app, use a newer yt-dlp that was downloaded from the Settings window.
_paths.use_updated_packages()
