"""Claude Code hook for the status pet.

Usage (from a hook): python hook.py <SessionStart|UserPromptSubmit|PreToolUse|
                                      PostToolUse|Notification|Stop|SessionEnd>

- Sets the pet's status (working / waiting / idle / celebrate) and a short
  description of the current tool for his speech bubble.
- Plays a sound when Claude needs you (toggle in the pet's right-click menu).
- Tracks open sessions in ~/.claude-pet/sessions.json, with the claude.exe
  process of each, so the pet can quit or hide when Claude does.
- Launches the pet if it isn't running.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

DIR = Path.home() / ".claude-pet"
STATUS = DIR / "status"
DETAIL = DIR / "detail"
TASK_START = DIR / "task_start"
SESSIONS = DIR / "sessions.json"
HEARTBEAT = DIR / "heartbeat"
LAUNCHING = DIR / "launching"
CONFIG = DIR / "config.json"
PET = Path(__file__).with_name("pet.py")
STALE_AFTER = 12 * 3600
CELEBRATE_AFTER = 30  # seconds of work before a finished task gets confetti

STATUS_FOR = {
    "SessionStart": "idle",
    "UserPromptSubmit": "working",
    "PreToolUse": "working",
    "PostToolUse": "working",
    "Notification": "waiting",
    "Stop": "idle",
    "SessionEnd": "idle",
}


def age(path):
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return float("inf")


# ---------------------------------------------------------------- processes

def process_table():
    """pid -> (parent pid, exe name) for every running process."""
    import ctypes
    from ctypes import wintypes

    class ENTRY(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260),
        ]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    table = {}
    entry = ENTRY()
    entry.dwSize = ctypes.sizeof(ENTRY)
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile.lower())
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return table


def claude_ancestor_pids():
    """(session pid, desktop app pid) for the nearest claude.exe ancestor.

    The app pid is the session's parent when that is also a claude.exe (the
    desktop app's main process, which owns the window); None for a plain CLI.
    """
    try:
        table = process_table()
    except Exception:
        return None, None
    pid = os.getpid()
    for _ in range(20):
        parent = table.get(pid, (0, ""))[0]
        if not parent or parent not in table:
            return None, None
        if table[parent][1] == "claude.exe":
            grand = table[parent][0]
            app = grand if grand in table and table[grand][1] == "claude.exe" else None
            return parent, app
        pid = parent
    return None, None


def pid_alive(pid):
    import ctypes

    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    k32.GetExitCodeProcess(handle, ctypes.byref(code))
    k32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


# ----------------------------------------------------------------- sessions

def load_sessions():
    try:
        data = json.loads(SESSIONS.read_text())
    except (OSError, ValueError):
        return {}
    now = time.time()
    live = {}
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        if val.get("pid"):
            if pid_alive(val["pid"]):
                live[key] = val
        elif now - val.get("ts", 0) < STALE_AFTER:
            live[key] = val
    return live


def launch_pet():
    if age(HEARTBEAT) < 5 or age(LAUNCHING) < 10:
        return
    LAUNCHING.write_text(str(time.time()))
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    subprocess.Popen(
        [str(pythonw if pythonw.exists() else exe), str(PET)],
        creationflags=0x00000008 | 0x08000000,  # DETACHED_PROCESS | CREATE_NO_WINDOW
        close_fds=True,
    )


# ------------------------------------------------------------ bubble / sound

def short_path(value):
    name = Path(str(value)).name if value else ""
    return name


def describe_tool(payload):
    """A few words about what Claude is doing, for the speech bubble."""
    name = payload.get("tool_name", "")
    args = payload.get("tool_input") or {}
    target = short_path(args.get("file_path") or args.get("notebook_path") or args.get("path"))
    if name in ("Edit", "MultiEdit", "NotebookEdit"):
        return f"Editing {target}" if target else "Editing a file"
    if name == "Write":
        return f"Writing {target}" if target else "Writing a file"
    if name == "Read":
        return f"Reading {target}" if target else "Reading a file"
    if name in ("Bash", "PowerShell"):
        words = str(args.get("command", "")).split()
        return "Running " + " ".join(words[:3]) if words else "Running a command"
    if name in ("Grep", "Glob"):
        return "Searching files"
    if name in ("WebSearch", "WebFetch"):
        return "Browsing the web"
    if name == "Agent":
        return "Running a subagent"
    if name == "Skill":
        return "Using a skill"
    if name.startswith("mcp__"):
        return "Using " + name.split("__")[-1].replace("_", " ")
    return name or "Working…"


def sound_enabled():
    try:
        return bool(json.loads(CONFIG.read_text()).get("sound", True))
    except (OSError, ValueError):
        return True


def beep():
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


# --------------------------------------------------------------------- main

def main():
    event = sys.argv[1] if len(sys.argv) > 1 else "Stop"
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    session_id = payload.get("session_id", "unknown")

    DIR.mkdir(parents=True, exist_ok=True)
    sessions = load_sessions()
    if event == "SessionEnd":
        sessions.pop(session_id, None)
    else:
        pid, app = claude_ancestor_pids()
        sessions[session_id] = {"ts": time.time(), "pid": pid, "app": app}
    SESSIONS.write_text(json.dumps(sessions))

    if not sessions:
        return

    status = STATUS_FOR.get(event, "idle")
    if event == "UserPromptSubmit":
        TASK_START.write_text(str(time.time()))
        DETAIL.write_text("Thinking…")
    elif event == "PreToolUse":
        DETAIL.write_text(describe_tool(payload))
    elif event == "PostToolUse":
        DETAIL.write_text("Thinking…")
    elif event == "Stop":
        if CELEBRATE_AFTER <= age(TASK_START) < 6 * 3600:
            status = "celebrate"
        TASK_START.unlink(missing_ok=True)
    elif event == "Notification" and sound_enabled():
        beep()

    STATUS.write_text(status)
    launch_pet()


if __name__ == "__main__":
    main()
