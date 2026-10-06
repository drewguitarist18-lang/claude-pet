# Claude Pet

Clawd, a small pixel companion that walks around your desktop and shows what
Claude Code is doing. Windows, Python 3 (tkinter only, no installs).

| State | What he does |
|---|---|
| idle | wanders, blinks, winks; sleeps after 5 quiet minutes |
| working | types on a little laptop; speech bubble shows the current tool |
| waiting | waves, says "Needs you!", plays a sound |
| celebrate | jumps with confetti after a task that took 30s+ |

Drag him onto any ledge and he patrols it. Right-click for outfits, sound
and quit.

## How it works

- `hook.py` runs from Claude Code hooks, writes state to `~/.claude-pet/`,
  tracks open sessions, and launches the pet.
- `pet.py` reads that state and animates. It hides when the Claude window is
  closed to the tray and quits when the last session ends.

## Install

Add hooks to `~/.claude/settings.json`, one per event, each running
`python "<path to>/hook.py" <Event>`, for: `SessionStart`, `UserPromptSubmit`,
`PreToolUse`, `PostToolUse`, `Notification`, `Stop`, `SessionEnd`.

Run him by hand (stays up without a session): `python pet.py --keep`
