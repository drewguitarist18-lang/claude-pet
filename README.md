# Claude Pet

Clawd, a small pixel pet who lives on your desktop (Windows, Mac or Linux), shows
what Claude Code is doing, and takes you to Claude in one click. Site: https://claude-pet-iota.vercel.app

## Download

**[ClaudePetSetup.exe](https://github.com/drewguitarist18-lang/claude-pet/releases/latest/download/ClaudePetSetup.exe)**
(Windows 10/11, about 10 MB, no Python or admin rights needed). It installs to
`%LOCALAPPDATA%\Programs\Claude Pet` and adds Clawd's hooks to
`~/.claude/settings.json`, backing that file up first. Uninstall from
Settings → Apps; that removes the hooks too.

**[ClaudePet-mac.dmg](https://github.com/drewguitarist18-lang/claude-pet/releases/latest/download/ClaudePet-mac.dmg)**
(macOS 11+). Drag **Claude Pet** into Applications and open it. It isn't signed, so the first
time: right-click it, choose **Open**, then **Open** again. On that first start he adds his hooks
to `~/.claude/settings.json` (backing it up) and a LaunchAgent so he starts when you sign in.
To remove him: run `"/Applications/Claude Pet.app/Contents/MacOS/claude-pet-cli" uninstall`,
then trash the app.

**[ClaudePet-linux-x86_64.tar.gz](https://github.com/drewguitarist18-lang/claude-pet/releases/latest/download/ClaudePet-linux-x86_64.tar.gz)**
(X11 or XWayland). Unpack it and run `./ClaudePet/install.sh`: he goes into
`~/.local/share/claude-pet` with a menu entry, his hooks and an autostart entry;
`~/.local/share/claude-pet/uninstall.sh` takes it all back out. Install `wmctrl` (or `xdotool`)
so clicking him can raise your terminal. Linux has no Claude desktop app, so with no session
open a click opens claude.ai.

## What he does

| State | What he does |
|---|---|
| idle | wanders, blinks, winks; sleeps after 5 quiet minutes |
| working | types on a little laptop; speech bubble shows the current tool |
| waiting | waves, says "Needs you!", plays a chime |
| celebrate | jumps with confetti after a task that took 30s+ |
| out of juice | asleep with "Out of juice · 8:10pm" when you hit your usage limit; wakes when it resets |

**Reactions:** a facepalm when a tool fails, fireworks when Claude runs `git commit` or `git push`.
Each subagent shows up as a tiny buddy beside him and walks off when it's done.

**Click him** to jump to Claude: the session that needs you first, else the latest one, or the
Claude app opens if no window is up. He hops with a few hearts.

**Energy:** he gets tired as the context window fills. Half-lidded at 50%,
yawning and slower at 75%, sweating with a "Context N% full" bubble at 90%.
A small context bar under his feet fills up with it.

**Always on screen** (the default): he starts when you sign in and stays up, napping
when nothing's running. Switch it off in his menu and he only shows while the
Claude desktop app is open (on Windows: its window is open or minimized) or Claude
Code runs in a terminal, and quits when the last session ends. Background sessions
(`claude -p`, the Agent SDK, Lithnode's agents) never wake him.

**In Lithnode:** while the [Lithnode](https://lithnode.com) app is open, Clawd turns into
Lithnode's white crab; close Lithnode and he's Clawd again.

Drag him onto any ledge and he patrols it. Right-click for his menu: status,
context used, today's sessions, tools and time worked, outfit tiles (a witch hat
and pumpkin join in October, a Santa hat in December), the chime and
context-bar switches, and quit.

## How it works

- `hook.py` runs from Claude Code hooks. It keeps one entry per session in
  `~/.claude-pet/sessions.json`, mirrors the latest status for the pet and
  launches him. Lithnode's Office reads the same file.
- `pet.py` is the desktop pet (tkinter, standard library only), with `pet_menu.py` for his menu.
- `desktop.py` is the per-OS part: finding and raising Claude's window, see-through windows
  (a key color on Windows, Tk's transparent windows on the Mac, the X11 Shape extension on
  Linux), one pet at a time, the chime and fonts.
- `shared.py` holds paths, session helpers and the process table (Toolhelp, `ps`, `/proc`).
- `packaging/` builds the installer: `claude_pet_main.py` is the entry for
  `ClaudePet.exe` (the pet) and `claude-pet-cli.exe` (`hook`, `install`,
  `uninstall`). Windows: `powershell -ExecutionPolicy Bypass -File packaging\build.ps1`
  (one-time setup is at the top of that file) makes `dist\ClaudePetSetup.exe`. Mac and
  Linux: `sh packaging/build.sh` makes the .dmg or the .tar.gz.
- `tests/smoke.py` runs the hook, the process helpers and the pet through every state.
  GitHub Actions (`.github/workflows/build.yml`) runs it on Windows, macOS and Linux, builds
  all three downloads, and puts them on a draft release for a `v*` tag.
- `site/` is the website (one static page).

## Install from source (plugin)

Needs Python 3 with tkinter on your PATH (as `python3` or `python`). Inside Claude Code:

```
/plugin marketplace add drewguitarist18-lang/claude-pet
/plugin install claude-pet@claude-pet
```

Use either the installer or the plugin, not both, or every event fires twice.
Run him by hand (stays up without a session): `python pet.py --keep`.

`~/.claude-pet/config.json` can set `"context_window"` (default 200000; it
switches to 1,000,000 on its own if a session goes past 200k).

Not affiliated with or endorsed by Anthropic.
