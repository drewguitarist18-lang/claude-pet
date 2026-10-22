"""State shared by the hook and the pet."""
import contextlib
import ctypes
import json
import os
import time
from pathlib import Path

DIR = Path.home() / ".claude-pet"
STATUS = DIR / "status"
DETAIL = DIR / "detail"
CONTEXT = DIR / "context.json"
SESSIONS = DIR / "sessions.json"
CONFIG = DIR / "config.json"
HEARTBEAT = DIR / "heartbeat"
REACT = DIR / "react.json"     # a one-off reaction for the pet: oops, commit, push
LIMIT = DIR / "limit.json"     # set while the usage limit is hit: when it resets
TODAY = DIR / "today.json"     # today's stats for the menu
STALE_AFTER = 12 * 3600  # sessions we can't tie to a process expire after this


def pid_alive(pid):
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    k32.GetExitCodeProcess(handle, ctypes.byref(code))
    k32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


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


def process_names():
    """Exe names (lowercase) of every running process."""
    return {name for _, name in process_table().values()}


def live_sessions():
    """{session id: entry} for sessions whose claude.exe is still running."""
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


LOCK = DIR / "sessions.lock"


@contextlib.contextmanager
def sessions_lock(timeout=5.0):
    """Serialize read-modify-write of sessions.json across hook processes.

    Uses an exclusive-create lock file. A lock older than the timeout is
    treated as left behind by a crashed hook and taken over.
    """
    deadline = time.time() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - LOCK.stat().st_mtime > timeout:
                    LOCK.unlink()
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                break  # give up waiting; better a rare lost update than a hung hook
            time.sleep(0.01)
        except OSError:
            break
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
            try:
                LOCK.unlink()
            except OSError:
                pass


def write_sessions(sessions):
    """Replace sessions.json atomically so readers never see a half-written file."""
    tmp = SESSIONS.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(sessions))
    for attempt in range(10):  # a reader may briefly hold the file open on Windows
        try:
            tmp.replace(SESSIONS)
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
    tmp.unlink(missing_ok=True)


def usage_limit(transcript_path):
    """(resets_at, limit type) if the newest main-thread reply is a usage-limit error, else None."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 200_000))
            tail = f.read().decode("utf-8", "ignore")
    except (OSError, TypeError):
        return None
    for line in reversed(tail.splitlines()):
        if '"assistant"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("type") != "assistant" or record.get("isSidechain"):
            continue
        if record.get("apiError") != "usage_limit_reached":
            return None
        info = (record.get("apiErrorParams") or {}).get("rate_limit_info") or record.get("quotaLimits") or {}
        return info.get("resetsAt"), info.get("rateLimitType") or ""
    return None
