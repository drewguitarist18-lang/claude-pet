"""Claude Code hook for the status pet and the Claude Office.

Usage (from a hook): python hook.py <Event>
Events: SessionStart UserPromptSubmit PreToolUse PostToolUse Notification
        Stop SubagentStart SubagentStop SessionEnd

- Keeps one entry per open session in ~/.claude-pet/sessions.json (status,
  current tool, context fill, project, subagents) for the office view.
- Mirrors the latest status/detail/context into small files for the pet.
- Plays a sound when Claude needs you (toggle in the pet's right-click menu).
- Launches the pet if it isn't running.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import shared
from shared import CONFIG, CONTEXT, DETAIL, DIR, HEARTBEAT, STATUS

LAUNCHING = DIR / "launching"
PET = Path(__file__).with_name("pet.py")
DEFAULT_WINDOW = 200_000  # override with "context_window" in config.json
CELEBRATE_AFTER = 30  # seconds of work before a finished task gets confetti
SUBAGENT_STALE = 30 * 60

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


def launch_pet():
    if age(HEARTBEAT) < 5 or age(LAUNCHING) < 10:
        return
    LAUNCHING.write_text(str(time.time()))
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):   # bundled in the Lithnode app: its windowless engine runs the pet
        command = [str(exe.with_name("lithnode-server.exe")), "pet"]
    else:
        pythonw = exe.with_name("pythonw.exe")
        command = [str(pythonw if pythonw.exists() else exe), str(PET)]
    subprocess.Popen(
        command,
        creationflags=0x00000008 | 0x08000000,  # DETACHED_PROCESS | CREATE_NO_WINDOW
        close_fds=True,
    )


# ------------------------------------------------------------ bubble / sound

def describe_tool(payload):
    """A few words about what Claude is doing, for the speech bubble."""
    name = payload.get("tool_name", "")
    args = payload.get("tool_input") or {}
    target = Path(str(args.get("file_path") or args.get("notebook_path")
                      or args.get("path") or "")).name
    if name in ("Edit", "MultiEdit", "NotebookEdit"):
        return f"Editing {target}" if target else "Editing a file"
    if name == "Write":
        return f"Writing {target}" if target else "Writing a file"
    if name == "Read":
        return f"Reading {target}" if target else "Reading a file"
    if name in ("Bash", "PowerShell"):
        summary = str(args.get("description") or "").strip()
        if summary:
            return summary
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


def context_tokens(transcript_path):
    """Tokens currently in context, from the newest main-thread usage record."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400_000))
            tail = f.read().decode("utf-8", "ignore")
    except (OSError, TypeError):
        return None
    for line in reversed(tail.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        usage = (record.get("message") or {}).get("usage")
        if record.get("isSidechain") or not usage:
            continue
        return sum(usage.get(k, 0) for k in (
            "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return None


def context_window(tokens):
    try:
        window = int(json.loads(CONFIG.read_text()).get("context_window", DEFAULT_WINDOW))
    except (OSError, ValueError, TypeError):
        window = DEFAULT_WINDOW
    if tokens > window:  # bigger than assumed (e.g. a 1M model)
        window = 1_000_000 if tokens <= 1_000_000 else tokens
    return window


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

def update_entry(entry, event, payload, now):
    """Apply one hook event to a session's entry; returns (status, detail)."""
    status = STATUS_FOR.get(event, "idle")
    detail = entry.get("detail", "")

    # Tool events from inside a subagent belong to that subagent's own block.
    sub = (entry.get("subagents") or {}).get(payload.get("agent_id"))
    if sub is not None and event in ("PreToolUse", "PostToolUse"):
        if event == "PreToolUse":  # keep showing the last action between tools
            sub["tools"] = sub.get("tools", 0) + 1
            sub["detail"] = describe_tool(payload)
        return entry.get("status", "idle"), detail

    if event == "UserPromptSubmit":
        entry["task_start"] = now
        detail = "Thinking…"
    elif event == "PreToolUse":
        entry["tools"] = entry.get("tools", 0) + 1
        detail = describe_tool(payload)
    elif event == "PostToolUse":
        detail = "Thinking…"
    elif event == "Stop":
        started = entry.pop("task_start", None)
        if started and CELEBRATE_AFTER <= now - started < 6 * 3600:
            status = "celebrate"
        entry["done"] = entry.get("done", 0) + 1
        detail = ""
    elif event == "SessionStart":
        detail = ""
    elif event in ("SubagentStart", "SubagentStop"):
        subs = entry.setdefault("subagents", {})
        agent_id = payload.get("agent_id") or payload.get("agent_type") or "agent"
        if event == "SubagentStart":
            subs[agent_id] = {"type": payload.get("agent_type") or "agent", "ts": now}
        else:
            subs.pop(agent_id, None)
        status = entry.get("status", "idle")  # subagents don't change the parent's status

    # Drop subagents that never reported a stop.
    entry["subagents"] = {
        k: v for k, v in entry.get("subagents", {}).items() if now - v["ts"] < SUBAGENT_STALE
    }

    tokens = context_tokens(payload.get("transcript_path"))
    if tokens is not None:
        entry["tokens"], entry["window"] = tokens, context_window(tokens)

    if status != entry.get("status") or event in ("PreToolUse", "UserPromptSubmit"):
        entry["status_ts"] = now
    entry["status"], entry["detail"] = status, detail
    return status, detail


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else "Stop"
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    session_id = payload.get("session_id", "unknown")
    now = time.time()

    DIR.mkdir(parents=True, exist_ok=True)
    pid, app = claude_ancestor_pids()  # slow-ish, so look it up before taking the lock
    status, detail, entry = "idle", "", None

    with shared.sessions_lock():  # several hooks can fire at once (parallel tools, subagents)
        sessions = shared.live_sessions()
        if event == "SessionEnd":
            sessions.pop(session_id, None)
        else:
            entry = sessions.setdefault(session_id, {})
            entry.setdefault("started", now)
            entry.update(ts=now, pid=pid, app=app)
            cwd = payload.get("cwd")
            if cwd:
                entry["cwd"], entry["project"] = cwd, Path(cwd).name or cwd
            status, detail = update_entry(entry, event, payload, now)
        shared.write_sessions(sessions)

    if not sessions or entry is None:
        return

    # Mirror the latest activity into the files the pet reads.
    STATUS.write_text(status)
    DETAIL.write_text(detail)
    if "tokens" in entry:
        CONTEXT.write_text(json.dumps({"tokens": entry["tokens"], "window": entry["window"]}))
    if event == "Notification" and sound_enabled():
        beep()
    launch_pet()


if __name__ == "__main__":
    main()
