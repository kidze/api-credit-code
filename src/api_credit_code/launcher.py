"""App icons: Start menu and Desktop shortcuts on Windows, an app in ~/Applications on a Mac, a menu entry on Linux.

The one-line installers run `--make-launcher` once. Every icon starts the app with --app: it opens a browser tab and
quits by itself a few minutes after its last tab is closed. The icons are made on your own computer, not downloaded,
so Windows and macOS have no download warning to show for them.
"""
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import APP_ID, APP_NAME, __version__
from .paths import static_dir

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"
DESCRIPTION = "Run your own Claude Code from a browser tab, on your monthly API credits"
BUNDLE_ID = "io.github.kidze.api-credit-code"


def start_command():
    """(program, arguments) that start this installed copy of the app without a console window."""
    if getattr(sys, "frozen", False):  # the Windows .exe or the Mac app build
        return sys.executable, ["--app"]
    exe = Path(sys.executable)
    if WINDOWS and exe.with_name("pythonw.exe").exists():
        exe = exe.with_name("pythonw.exe")
    return str(exe), ["-m", "api_credit_code", "--app"]


# Windows shortcuts go through PowerShell's WScript.Shell, the standard way to write a .lnk. Paths and names travel
# in environment variables, so nothing needs quoting.
_PS_MAKE = r"""
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
  if (-not $dir) { continue }
  $path = Join-Path $dir $env:ACC_LNK
  $link = $shell.CreateShortcut($path)
  $link.TargetPath = $env:ACC_TARGET
  $link.Arguments = $env:ACC_ARGS
  $link.IconLocation = $env:ACC_ICON
  $link.WorkingDirectory = $env:USERPROFILE
  $link.Description = $env:ACC_DESC
  $link.Save()
  Write-Output $path
}
"""
_PS_REMOVE = r"""
foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
  if (-not $dir) { continue }
  $path = Join-Path $dir $env:ACC_LNK
  if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force; Write-Output $path }
}
"""


def _powershell(script, extra_env):
    env = {**os.environ, "ACC_LNK": f"{APP_NAME}.lnk", **extra_env}
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                         capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
                         creationflags=0x08000000)
    if out.returncode:
        raise OSError((out.stderr or out.stdout or "PowerShell failed").strip().splitlines()[-1])
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def _mac_app():
    return Path.home() / "Applications" / f"{APP_NAME}.app"


def _linux_entry():
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "applications" / f"{APP_ID}.desktop"


def make():
    """Create the icons. Returns the paths made."""
    prog, args = start_command()
    if WINDOWS:
        icon = static_dir() / "icon.ico"
        return _powershell(_PS_MAKE, {"ACC_TARGET": prog, "ACC_ARGS": subprocess.list2cmdline(args),
                                      "ACC_ICON": f"{icon},0", "ACC_DESC": DESCRIPTION})
    if MAC:
        app = _mac_app()
        contents = app / "Contents"
        (contents / "MacOS").mkdir(parents=True, exist_ok=True)
        (contents / "Resources").mkdir(exist_ok=True)
        # Started from Finder, an app gets a bare PATH; keep the one you installed with, so Claude Code is found.
        path = os.pathsep.join(dict.fromkeys([str(Path.home() / ".local" / "bin")]
                                             + os.environ.get("PATH", "").split(os.pathsep)))
        script = ("#!/bin/bash\n"
                  "# Starts API Credit Code in the background and returns at once,\n"
                  "# so opening the app again just opens another browser tab.\n"
                  f"export PATH={shlex.quote(path)}\n"
                  f"nohup {shlex.join([prog, *args])} >/dev/null 2>&1 &\n")
        exe = contents / "MacOS" / APP_ID
        exe.write_text(script, encoding="utf-8")
        os.chmod(exe, 0o755)
        shutil.copyfile(static_dir() / "AppIcon.icns", contents / "Resources" / "AppIcon.icns")
        with open(contents / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME, "CFBundleIdentifier": BUNDLE_ID,
                           "CFBundleExecutable": APP_ID, "CFBundleIconFile": "AppIcon", "CFBundlePackageType": "APPL",
                           "CFBundleShortVersionString": __version__, "CFBundleVersion": __version__,
                           "LSUIElement": True, "LSMinimumSystemVersion": "11.0"}, f)
        os.utime(app)  # so Finder notices the new icon
        return [str(app)]
    entry = _linux_entry()
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("[Desktop Entry]\nType=Application\n"
                     f"Name={APP_NAME}\nComment={DESCRIPTION}\n"
                     f"Exec={shlex.join([prog, *args])}\n"
                     f"Icon={static_dir() / 'icon-512.png'}\nTerminal=false\nCategories=Development;\n",
                     encoding="utf-8")
    return [str(entry)]


def remove():
    """Delete the icons. Returns the paths removed."""
    if WINDOWS:
        return _powershell(_PS_REMOVE, {})
    target = _mac_app() if MAC else _linux_entry()
    if not target.exists():
        return []
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return [str(target)]
