# PyInstaller build: two programs sharing one folder (see claude_pet_main.py).
from pathlib import Path

HERE = Path(SPECPATH)
ROOT = HERE.parent

a = Analysis(
    [str(HERE / "claude_pet_main.py")],
    pathex=[str(ROOT)],
    hiddenimports=["hook", "pet", "shared", "tkinter", "winsound"],
    excludes=["test", "unittest", "pydoc_data", "email", "http", "xml", "sqlite3"],
)
pyz = PYZ(a.pure)
icon = str(HERE / "claude-pet.ico")
pet = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ClaudePet", console=False, icon=icon)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="claude-pet-cli", console=True, icon=icon)
coll = COLLECT(pet, cli, a.binaries, a.datas, name="ClaudePet")
