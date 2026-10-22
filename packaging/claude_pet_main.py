"""Entry point for the installed Claude Pet app (built by packaging/build.ps1 on Windows,
packaging/build.sh on the Mac and Linux).

ClaudePet       (no console)  runs Clawd; the hook starts him when Claude Code is in use
claude-pet-cli  (console)     `hook <Event>`          the Claude Code hook that feeds him
                              `install` / `uninstall` add or remove the hooks in ~/.claude/settings.json
                              (and, off Windows, starting him when you sign in)
(both .exe on Windows). The Windows installer runs `install`; on the Mac and Linux the pet runs it
himself the first time he starts from where he's installed.
"""
import json
import os
import runpy
import shutil
import sys
from pathlib import Path

EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure",
          "Notification", "Stop", "StopFailure", "SubagentStart", "SubagentStop", "SessionEnd")
SETTINGS = Path.home() / ".claude" / "settings.json"
WINDOWS = sys.platform == "win32"
SET_UP = Path.home() / ".claude-pet" / "installed"   # off Windows: the first start added the hooks


def _cli():
    return Path(sys.executable).with_name("claude-pet-cli.exe" if WINDOWS else "claude-pet-cli")


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
    if not WINDOWS:   # the Windows installer sets this up itself
        import shared
        shared.set_start_at_login(True)
        SET_UP.parent.mkdir(parents=True, exist_ok=True)
        SET_UP.write_text(str(_cli()))


def _first_start():
    """Off Windows there's no installer: add the hooks the first time the pet starts from a real
    install (not from the disk image it came on, or a folder that's about to move)."""
    exe = str(Path(sys.executable).resolve())
    if WINDOWS or not getattr(sys, "frozen", False) or exe.startswith(("/Volumes/", "/private/var/folders/")):
        return
    try:
        if SET_UP.read_text().strip() == str(_cli()):
            return
    except OSError:
        pass
    try:
        install()
    except (OSError, ValueError):
        pass


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
    if not WINDOWS:
        import shared
        shared.set_start_at_login(False)


def main():
    args = sys.argv[1:]
    if Path(sys.executable).stem.lower() != "claude-pet-cli":
        _first_start()
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
