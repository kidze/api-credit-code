"""Where things live: this app's own folder (your key, your chats, a log) and Claude Code's files it reads."""
import os
import sys
from pathlib import Path

from . import APP_ID


def data_dir():
    """This app's folder in your user profile. API_CREDIT_CODE_HOME moves it (the tests use that)."""
    override = os.environ.get("API_CREDIT_CODE_HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_ID
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_ID


def claude_dir():
    """Claude Code's own folder: ~/.claude, unless CLAUDE_CONFIG_DIR points elsewhere."""
    moved = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(moved).expanduser() if moved else Path.home() / ".claude"


def claude_state_file():
    """Claude Code's ~/.claude.json: among other things, the folders you have trusted."""
    moved = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(moved).expanduser() / ".claude.json" if moved else Path.home() / ".claude.json"


def static_dir():
    """The page's files, inside the package (also inside the Windows and Mac app builds)."""
    return Path(__file__).resolve().parent / "static"
