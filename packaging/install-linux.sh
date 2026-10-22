#!/bin/sh
# Installs Claude Pet for this user: the app into ~/.local/share/claude-pet, a menu entry, his
# Claude Code hooks (backing up ~/.claude/settings.json first) and starting him when you sign in.
# ~/.local/share/claude-pet/uninstall.sh (or ./install.sh --uninstall) takes all of that back out.
set -e
src=$(cd "$(dirname "$0")" && pwd)
dest="${XDG_DATA_HOME:-$HOME/.local/share}/claude-pet"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
if [ "$1" = "--uninstall" ] || [ "$(basename "$0")" = uninstall.sh ]; then
  pkill -x ClaudePet 2>/dev/null || true
  [ -x "$dest/claude-pet-cli" ] && "$dest/claude-pet-cli" uninstall
  rm -rf "$dest" "$apps/claude-pet.desktop"
  echo "Claude Pet is uninstalled."
  exit 0
fi
pkill -x ClaudePet 2>/dev/null || true
mkdir -p "$dest" "$apps"
cp -R "$src/." "$dest/"
rm -f "$dest/install.sh"
cp "$src/install.sh" "$dest/uninstall.sh"
cat > "$apps/claude-pet.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Claude Pet
Comment=Clawd, the Claude Code status pet
Exec="$dest/ClaudePet"
Icon=$dest/claude-pet.png
Categories=Utility;
DESKTOP
"$dest/claude-pet-cli" install
nohup "$dest/ClaudePet" >/dev/null 2>&1 &
echo "Claude Pet is installed and on your desktop. To remove him: $dest/uninstall.sh"
command -v wmctrl >/dev/null || command -v xdotool >/dev/null || \
  echo "Tip: install wmctrl (or xdotool) so clicking Clawd can bring your terminal to the front."
