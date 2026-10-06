# Claude Pet

Clawd, a small pixel companion that walks around your desktop and shows what
Claude Code is doing, plus a **Claude Office** that shows every open session
as a little Clawd at a desk. Windows, Python 3 (standard library only).

## The pet

| State | What he does |
|---|---|
| idle | wanders, blinks, winks; sleeps after 5 quiet minutes |
| working | types on a little laptop; speech bubble shows the current tool |
| waiting | waves, says "Needs you!", plays a sound |
| celebrate | jumps with confetti after a task that took 30s+ |

**Energy:** he gets tired as the context window fills. Half-lidded at 50%,
yawning and slower at 75%, sweating with a "Context N% full" bubble at 90%.
A small energy bar sits under his feet.

Drag him onto any ledge and he patrols it. Right-click for the office,
outfits, sound, the energy bar and quit.

## The office

Right-click the pet, then **Open Claude Office** (or browse to
http://127.0.0.1:8765). Each session gets a station: its Clawd, a floating
screen with the current action, an energy bar, and little colored helpers for
running subagents. Click a station for details. Light and dark themes follow
your system.

## How it works

- `hook.py` runs from Claude Code hooks. It keeps one entry per session in
  `~/.claude-pet/sessions.json` and launches the pet.
- `pet.py` is the desktop pet. It hides when the Claude window is closed to
  the tray, quits when the last session ends, and serves the office.
- `office.py` + `office.html` are the office server and page (localhost only).
- `shared.py` holds paths and session helpers used by all of the above.

## Install

Add hooks to `~/.claude/settings.json`, one per event, each running
`python "<path to>/hook.py" <Event>`, for: `SessionStart`, `UserPromptSubmit`,
`PreToolUse`, `PostToolUse`, `Notification`, `Stop`, `SubagentStart`,
`SubagentStop`, `SessionEnd`.

Run him by hand (stays up without a session): `python pet.py --keep`.
Run just the office: `python office.py`.

`~/.claude-pet/config.json` can set `"context_window"` (default 200000; it
switches to 1,000,000 on its own if a session goes past 200k).
