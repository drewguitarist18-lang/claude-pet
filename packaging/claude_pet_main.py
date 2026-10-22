"""Entry point for the installed Claude Pet app (built by packaging/build.ps1).

ClaudePet.exe       (no console)  runs Clawd; the hook starts him when Claude Code is in use
claude-pet-cli.exe  (console)     `hook <Event>`          the Claude Code hook that feeds him
                                  `install` / `uninstall` add or remove the hooks in ~/.claude/settings.json
"""
import json
import os
import runpy
import shutil
import sys
from pathlib import Path

EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Notification",
          "Stop", "SubagentStart", "SubagentStop", "SessionEnd")
SETTINGS = Path.home() / ".claude" / "settings.json"


def _cli():
    return Path(sys.executable).with_name("claude-pet-cli.exe")


def _is_pet_hook(command):
    """Any copy of the pet's hook: this app's, Lithnode's bundled one, or Claude Pet run from source.
    One pet at a time, so installing replaces them all."""
    c = str(command).replace("\\", "/").lower()
    return "claude-pet-cli" in c or "claude pet/hook.py" in c or ("lithnode-cli" in c and " hook " in c + " ")


def _is_ours(command):
    return "claude-pet-cli" in str(command).lower()


def _strip(hooks, match):
    for event in list(hooks):
        kept = []
        for entry in hooks[event] if isinstance(hooks[event], list) else []:
            inner = [h for h in entry.get("hooks", []) if not match(h.get("command", ""))]
            if inner:
                kept.append({**entry, "hooks": inner})
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]


def _load():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _save(data):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS.with_suffix(".json.claude-pet-tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, SETTINGS)


def install():
    data = _load()   # a settings file that isn't valid JSON raises here: better than overwriting it
    backup = SETTINGS.with_name("settings.json.before-claude-pet")
    if SETTINGS.exists() and not backup.exists():
        shutil.copy2(SETTINGS, backup)
    hooks = data.setdefault("hooks", {})
    _strip(hooks, _is_pet_hook)
    cli = _cli().as_posix()
    for event in EVENTS:
        hooks.setdefault(event, []).append({"hooks": [{"type": "command", "command": f'"{cli}" hook {event}'}]})
    _save(data)


def uninstall():
    if not SETTINGS.exists():
        return
    data = _load()
    hooks = data.get("hooks") or {}
    before = json.dumps(hooks)
    _strip(hooks, _is_ours)   # leaves Lithnode's and anyone else's hooks alone
    if json.dumps(hooks) != before:
        if not hooks:
            data.pop("hooks", None)
        _save(data)


def main():
    args = sys.argv[1:]
    if Path(sys.executable).stem.lower() != "claude-pet-cli":
        sys.argv = ["pet.py"]
        runpy.run_module("pet", run_name="__main__")
    elif args[:1] == ["hook"]:
        sys.argv = ["hook.py", *args[1:]]
        runpy.run_module("hook", run_name="__main__")
    elif args[:1] == ["install"]:
        install()
    elif args[:1] == ["uninstall"]:
        uninstall()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
