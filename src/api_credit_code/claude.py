"""Finding and starting your own Claude Code.

Every message runs `claude -p` (Claude Code without its terminal screen) in the chat's folder, with your API key.
That is the use Anthropic's monthly API credits cover, and it loads the same CLAUDE.md, memory, skills and MCP
servers as running `claude` in that folder yourself.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000  # Windows: no console window pops up for Claude Code or the commands it runs

# Manual and Accept edits need Claude Code's permission channel and its -p behaviour from this version on.
MIN_VERSION = (2, 1, 302)

MODES = {"auto": "Auto", "default": "Manual", "acceptEdits": "Accept edits", "plan": "Plan"}
HOST_MODES = {"default", "acceptEdits"}  # modes where Claude asks you, through the page, before acting

PROMPT = ("You are answering through API Credit Code, a local chat window that runs Claude Code once per message "
          "in the folder the user picked. Format your answers for a chat window: Markdown is rendered. "
          "Interactive prompts can't be answered here, so ask any question you have in your reply.")

# Each of these outranks ANTHROPIC_API_KEY, so with one set a run would not be billed to the key.
OUTRANK_KEY = {"ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"}
# Set by a Claude Code session for its own child processes; a chat run must start as its own top-level session.
PARENT_VARS = {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH",
               "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ATTENDED",
               "CLAUDE_CODE_ENVIRONMENT_KIND", "CLAUDE_CODE_WORKER_EPOCH", "CLAUDE_CODE_SSE_PORT"}


def popen_kwargs():
    """Windows: no console windows. Elsewhere: its own process group, so Stop can end every command it started."""
    return {"creationflags": CREATE_NO_WINDOW} if WINDOWS else {"start_new_session": True}


def base_env():
    return {k: v for k, v in os.environ.items()
            if k not in OUTRANK_KEY and k not in PARENT_VARS
            and not k.startswith(("CLAUDE_CODE_BRIDGE_", "CLAUDE_CODE_MESSAGING_"))}


def child_env(key):
    env = base_env()
    env["ANTHROPIC_API_KEY"] = key
    # Commands, hooks and MCP servers that Claude Code starts don't get the key.
    env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] = "1"
    return env


def _login_shell_claude():
    """macOS/Linux, started from an app icon: PATH is minimal, so ask your login shell where claude is."""
    shell = os.environ.get("SHELL") or ("/bin/zsh" if sys.platform == "darwin" else "/bin/sh")
    try:
        out = subprocess.run([shell, "-lc", "command -v claude"], capture_output=True, text=True, timeout=10,
                             stdin=subprocess.DEVNULL).stdout.strip().splitlines()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out[-1] if out and os.path.isfile(out[-1]) else None


def find():
    """The command that starts Claude Code, as a list, or None when it isn't installed."""
    override = os.environ.get("API_CREDIT_CODE_CLAUDE")  # the tests point this at a stand-in
    if override:
        try:
            cmd = json.loads(override)
        except ValueError:
            cmd = override
        return [str(c) for c in cmd] if isinstance(cmd, list) else [str(cmd)]
    home = Path.home()
    exe = ".exe" if WINDOWS else ""
    candidates = [shutil.which("claude"), home / ".local" / "bin" / f"claude{exe}",
                  home / ".claude" / "local" / f"claude{exe}"]
    if WINDOWS:
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Links" / "claude.exe")
        if os.environ.get("APPDATA"):
            candidates.append(Path(os.environ["APPDATA"]) / "npm" / "claude.cmd")
    else:
        candidates += ["/opt/homebrew/bin/claude", "/usr/local/bin/claude", home / ".npm-global" / "bin" / "claude",
                       home / ".bun" / "bin" / "claude"]
    found = [str(c) for c in candidates if c and os.path.isfile(c)]
    if WINDOWS:  # the real program beats npm's claude.cmd wrapper
        found.sort(key=lambda c: not c.lower().endswith(".exe"))
    if not found and not WINDOWS:
        shell_says = _login_shell_claude()
        found = [shell_says] if shell_says else []
    return [found[0]] if found else None


def version(cmd):
    """Claude Code's version as (major, minor, patch), or None if it didn't say."""
    try:
        out = subprocess.run([*cmd, "--version"], capture_output=True, text=True, timeout=60, env=base_env(),
                             stdin=subprocess.DEVNULL, **popen_kwargs()).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out or "")
    return tuple(int(x) for x in m.groups()) if m else None


def build_args(cmd, *, sid, resume, model, effort, budget, mode):
    """One message's command line. The message itself goes in on stdin, as a stream-json line."""
    args = [*cmd, "-p", "--output-format", "stream-json", "--input-format", "stream-json", "--verbose",
            "--include-partial-messages", "--model", model, "--effort", effort, "--max-budget-usd", f"{budget:.2f}",
            "--append-system-prompt", PROMPT, "--permission-mode", mode]
    if mode in HOST_MODES:
        # Claude Code sends each "may I?" to this app, which shows it in the page. Claude's own question tool is
        # left out: a question it asked there would wait for an answer this app can't give.
        args += ["--permission-prompt-tool", "stdio", "--disallowedTools", "AskUserQuestion"]
    else:
        # Auto decides by itself; Plan only reads and writes a plan. Anything that would still ask is declined.
        args += ["--permission-prompts", "none"]
    args += ["--resume" if resume else "--session-id", sid]  # every message passes its mode, resumed or not
    return args


def kill_tree(proc):
    """End Claude Code and everything it started."""
    if not proc or proc.poll() is not None:
        return
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                       creationflags=CREATE_NO_WINDOW)
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            return
        try:
            proc.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            continue
