#!/bin/sh
# Runs a command where it can show windows: as is on Windows and the Mac; on Linux under a virtual
# X screen with a blue desktop, so screenshots show what's see-through.
if [ "$(uname)" = Linux ]; then
  exec xvfb-run -a -s "-screen 0 1280x800x24" sh -c 'xsetroot -solid "#4a7ab0"; exec "$@"' sh "$@"
fi
exec "$@"
