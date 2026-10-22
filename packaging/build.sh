#!/bin/sh
# Builds Claude Pet on the Mac or Linux (Windows: packaging/build.ps1).
#   Mac:   dist/ClaudePet-mac.dmg            ("Claude Pet.app"; drag it to Applications)
#   Linux: dist/ClaudePet-linux-x86_64.tar.gz (unpack, then ./install.sh)
# Needs Python 3 with tkinter; PyInstaller goes into packaging/.venv-build the first time.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(dirname "$here")
py="$here/.venv-build/bin/python"
if [ ! -x "$py" ]; then
  python3 -m venv "$here/.venv-build"
  "$py" -m pip install --quiet pyinstaller
fi
"$py" "$here/make_art.py"
"$py" -m PyInstaller --noconfirm --clean --log-level WARN --distpath "$root/dist" --workpath "$root/build" "$here/claude-pet.spec"
cd "$root/dist"
if [ "$(uname)" = Darwin ]; then
  rm -rf dmg ClaudePet-mac.dmg
  mkdir dmg
  cp -R "Claude Pet.app" dmg/
  ln -s /Applications dmg/Applications
  hdiutil create -quiet -volname "Claude Pet" -srcfolder dmg -ov -format UDZO ClaudePet-mac.dmg
  rm -rf dmg
  ls -lh ClaudePet-mac.dmg
else
  cp "$here/install-linux.sh" ClaudePet/install.sh
  cp "$here/claude-pet.png" ClaudePet/claude-pet.png
  chmod +x ClaudePet/install.sh
  tar -czf ClaudePet-linux-x86_64.tar.gz ClaudePet
  ls -lh ClaudePet-linux-x86_64.tar.gz
fi
