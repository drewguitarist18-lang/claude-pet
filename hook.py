"""Claude Code hook for Clawd, the status pet.

Usage (from a hook): python hook.py <Event>
Events: SessionStart UserPromptSubmit PreToolUse PostToolUse PostToolUseFailure
        Notification Stop StopFailure SubagentStart SubagentStop SessionEnd

- Keeps one entry per open session in ~/.claude-pet/sessions.json (status,
  current tool, context fill, project, subagents). Lithnode's Office reads it too.
- Mirrors the latest status/detail/context into small files for the pet.
- Tells the pet about tool failures, git commits/pushes and a hit usage limit, and
  keeps today's stats (sessions, tools, time worked) for his menu.
- Plays a sound when Claude needs you (toggle in the pet's right-click menu).
- Launches the pet if it isn't running, unless the session is a background
  agent (claude -p, the Agent SDK, Lithnode's agents): those never bring him up.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import shared
from shared import CONFIG, CONTEXT, DETAIL, DIR, HEARTBEAT, LIMIT, REACT, STATUS, TODAY

LAUNCHING = DIR / "launching"
PET = Path(__file__).with_name("pet.py")
DEFAULT_WINDOW = 200_000  # override with "context_window" in config.json
CELEBRATE_AFTER = 30  # seconds of work before a finished task gets confetti
SUBAGENT_STALE = 30 * 60
GIT = re.compile(r"\bgit\s+(?:-[Cc]\s+\S+\s+|--\S+\s+)*(commit|push)\b")  # git [-C dir] commit|push

STATUS_FOR = {
    "SessionStart": "idle",
    "UserPromptSubmit": "working",
    "PreToolUse": "working",
    "PostToolUse": "working",
    "PostToolUseFailure": "working",
    "Notification": "waiting",
    "Stop": "idle",
    "StopFailure": "idle",
    "SessionEnd": "idle",
}


def age(path):
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return float("inf")


# ---------------------------------------------------------------- processes

def claude_ancestor_pids():
    """(session pid, desktop app pid) for the nearest Claude ancestor (claude.exe, or claude
    off Windows).

    The app pid is the session's parent when that is also a Claude process (the
    desktop app's main process, which owns the window); None for a plain CLI.
    """
    try:
        table = shared.process_table()
    except Exception:
        return None, None
    pid = os.getpid()
    for _ in range(20):
        parent = table.get(pid, (0, ""))[0]
        if not parent or parent not in table:
            return None, None
        if table[parent][1] == shared.CLAUDE_EXE:
            grand = table[parent][0]
            app = grand if grand in table and table[grand][1] == shared.CLAUDE_EXE else None
            return parent, app
        pid = parent
    return None, None


def headless():
    """True for sessions nobody is looking at: claude -p, Agent SDK apps, Lithnode's agents.
    The desktop app runs on the SDK too, but says so with its own entrypoint."""
    entry = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")
    return bool(os.environ.get("LITHNODE_AGENT")) or entry.startswith("sdk")


def launch_pet():
    if age(HEARTBEAT) < 5 or age(LAUNCHING) < 10:
        return
    LAUNCHING.write_text(str(time.time()))
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):
        # the Claude Pet app ships ClaudePet(.exe); inside the Lithnode app its windowless engine runs the pet
        command = shared.pet_command()
        if not Path(command[-1]).exists():
            command = [str(exe.with_name("lithnode-server.exe")), "pet"]
    else:
        pythonw = exe.with_name("pythonw.exe")
        command = [str(pythonw if pythonw.exists() else exe), str(PET)]
    if shared.WINDOWS:
        detach = {"creationflags": 0x00000008 | 0x08000000}  # DETACHED_PROCESS | CREATE_NO_WINDOW
    else:
        detach = {"start_new_session": True, "stdin": subprocess.DEVNULL,
                  "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    subprocess.Popen(command, close_fds=True, **detach)


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
    import desktop

    desktop.chime()


def reaction(event, payload):
    """'oops' when a tool fails, 'commit' / 'push' when git does that; None otherwise."""
    if payload.get("agent_id"):
        return None   # only the main thread's
    if event == "PostToolUseFailure" and not payload.get("is_interrupt"):
        return "oops"
    if event == "PostToolUse" and payload.get("tool_name") in ("Bash", "PowerShell"):
        found = GIT.findall(str((payload.get("tool_input") or {}).get("command", "")))
        if found:
            return "push" if "push" in found else "commit"
    return None


def count_today(session_id, event, payload, entry, now):
    """Add this event to today's stats (call under the sessions lock)."""
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    try:
        stats = json.loads(TODAY.read_text())
    except (OSError, ValueError):
        stats = {}
    if stats.get("date") != today:
        stats = {"date": today, "sessions": [], "tools": 0, "tasks": 0, "work": 0.0}
    if session_id not in stats["sessions"]:
        stats["sessions"].append(session_id)
    if event == "PreToolUse":
        stats["tools"] += 1
    if event in ("Stop", "StopFailure") and entry.get("worked"):
        stats["work"] += entry.pop("worked")
        stats["tasks"] += event == "Stop"
    TODAY.write_text(json.dumps(stats))


# --------------------------------------------------------------------- main

def update_entry(entry, event, payload, now):
    """Apply one hook event to a session's entry; returns (status, detail)."""
    status = STATUS_FOR.get(event, "idle")
    detail = entry.get("detail", "")

    # Tool events from inside a subagent belong to that subagent's own block.
    sub = (entry.get("subagents") or {}).get(payload.get("agent_id"))
    if sub is not None and event in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
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
    elif event in ("PostToolUse", "PostToolUseFailure"):
        detail = "Thinking…"
    elif event in ("Stop", "StopFailure"):
        started = entry.pop("task_start", None)
        if started and now - started < 6 * 3600:
            entry["worked"] = now - started
            if event == "Stop" and now - started >= CELEBRATE_AFTER:
                status = "celebrate"
        if event == "Stop":
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
            entry.update(ts=now, pid=pid, app=app, headless=headless())
            cwd = payload.get("cwd")
            if cwd:
                entry["cwd"], entry["project"] = cwd, Path(cwd).name or cwd
            if payload.get("transcript_path"):
                entry["transcript"] = payload["transcript_path"]
            status, detail = update_entry(entry, event, payload, now)
            if not entry["headless"]:
                try:
                    count_today(session_id, event, payload, entry, now)
                except OSError:
                    pass
        shared.write_sessions(sessions)

    if not sessions or entry is None:
        return

    # Mirror the latest activity into the files the pet reads.
    STATUS.write_text(status)
    DETAIL.write_text(detail)
    if "tokens" in entry:
        CONTEXT.write_text(json.dumps({"tokens": entry["tokens"], "window": entry["window"]}))
    # Any session shares the account's limits: a failed turn may mean it's hit, a reply means it isn't.
    if event == "StopFailure":
        limit = shared.usage_limit(payload.get("transcript_path"))
        if limit:
            LIMIT.write_text(json.dumps({"resets_at": limit[0], "type": limit[1]}))
    elif event in ("PreToolUse", "PostToolUse", "Stop"):
        LIMIT.unlink(missing_ok=True)
    if entry.get("headless"):
        return
    kind = reaction(event, payload)
    if kind:
        REACT.write_text(json.dumps({"kind": kind, "ts": now}))
    if event == "Notification" and sound_enabled():
        beep()
    launch_pet()


if __name__ == "__main__":
    main()
