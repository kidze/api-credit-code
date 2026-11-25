# PyInstaller recipe for the downloadable apps: a folder with "API Credit Code.exe" on Windows (packaged into an
# installer by windows-installer.iss), "API Credit Code.app" on macOS. From the repository root:
#
#   pyinstaller --noconfirm --clean packaging/api-credit-code.spec
#
# The app has no console window; it logs to app.log in its data folder.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 (PyInstaller provides SPECPATH)
SRC = ROOT / "src"
STATIC = SRC / "api_credit_code" / "static"
NAME = "API Credit Code"
MAC = sys.platform == "darwin"

sys.path.insert(0, str(SRC))
from api_credit_code import __version__  # noqa: E402

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(SRC)],
    datas=[(str(STATIC), "api_credit_code/static")],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    upx=False,  # packed programs look suspicious to antivirus software
    icon=str(STATIC / ("AppIcon.icns" if MAC else "icon.ico")),
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name=NAME)  # noqa: F821

if MAC:
    app = BUNDLE(  # noqa: F821
        coll,
        name=f"{NAME}.app",
        icon=str(STATIC / "AppIcon.icns"),
        bundle_identifier="io.github.kidze.api-credit-code",
        version=__version__,
        info_plist={
            "CFBundleDisplayName": NAME,
            "CFBundleShortVersionString": __version__,
            "LSUIElement": True,  # no Dock icon: the app lives in a browser tab
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
        },
    )
