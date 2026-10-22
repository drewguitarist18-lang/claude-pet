# PyInstaller build: two programs sharing one folder (see claude_pet_main.py). On the Mac the
# folder goes into "Claude Pet.app" (no Dock icon: he lives on the desktop, not in the Dock).
import sys
from pathlib import Path

HERE = Path(SPECPATH)
ROOT = HERE.parent
WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"

a = Analysis(
    [str(HERE / "claude_pet_main.py")],
    pathex=[str(ROOT)],
    hiddenimports=["hook", "pet", "pet_menu", "desktop", "shared", "tkinter"] + (["winsound"] if WINDOWS else []),
    excludes=["test", "unittest", "pydoc_data", "email", "http", "xml", "sqlite3"],
)
pyz = PYZ(a.pure)
icon = str(HERE / ("claude-pet.ico" if WINDOWS else "claude-pet.icns" if MAC else "claude-pet.png"))
pet = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ClaudePet", console=False, icon=icon)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="claude-pet-cli", console=True, icon=icon)
coll = COLLECT(pet, cli, a.binaries, a.datas, name="ClaudePet")
if MAC:
    app = BUNDLE(coll, name="Claude Pet.app", icon=icon, bundle_identifier="com.claudepet.pet",
                 version="1.2.0", info_plist={"LSUIElement": True, "NSHighResolutionCapable": True,
                                              "CFBundleShortVersionString": "1.2.0"})
