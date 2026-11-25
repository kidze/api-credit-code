"""The folders a chat can run in: the ones you already trust in Claude Code, plus your home folder.

The first time you open a folder in Claude Code (`claude` in a terminal), it asks whether you trust that folder and
remembers the answer in ~/.claude.json. `claude -p`, which this app runs, never asks: it applies a folder's own
settings (hooks, environment variables, MCP servers) straight away. So this app only offers folders you have already
said yes to. Your home folder is offered too, because its Claude settings are your own user settings.
To add a folder: open it once with `claude` in a terminal and say yes.
"""
import json
import os
from pathlib import Path


def _key(path):
    return os.path.normcase(os.path.normpath(str(path)))


def _recency(info):
    best = 0
    for k in ("lastSessionModified", "lastStartTime"):
        v = info.get(k)
        if isinstance(v, (int, float)) and v > best:
            best = v
    return best


def trusted(state_file, home=None):
    """[{"path", "name"}], most recently used first, every one an existing folder; home last unless it was used."""
    home = Path(home) if home else Path.home()
    try:
        data = json.loads(Path(state_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    projects = data.get("projects") if isinstance(data, dict) else None
    found = {}
    for raw, info in (projects if isinstance(projects, dict) else {}).items():
        if not isinstance(info, dict) or info.get("hasTrustDialogAccepted") is not True:
            continue
        path = os.path.normpath(raw)
        if not os.path.isdir(path):
            continue
        k = _key(path)
        found[k] = max(found.get(k, (0, path)), (_recency(info), path))
    if _key(home) not in found and home.is_dir():
        found[_key(home)] = (-1, os.path.normpath(str(home)))
    items = sorted(found.values(), key=lambda t: (-t[0], t[1].lower()))
    return [{"path": p, "name": label(p, home)} for _, p in items]


def label(path, home=None):
    """A short name for a folder: its own name, ~ for home, or the drive for a drive's top."""
    home = Path(home) if home else Path.home()
    if _key(path) == _key(home):
        return "~ (home)"
    name = Path(path).name
    return name or str(path)


def match(path, folders):
    """The trusted folder that `path` names, spelled the way it is listed, or None. A chat runs in that spelling,
    not in whatever the request sent."""
    if not path:
        return None
    k = _key(path)
    return next((f["path"] for f in folders if _key(f["path"]) == k), None)


def allowed(path, folders):
    return match(path, folders) is not None
