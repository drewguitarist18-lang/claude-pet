"""State shared by the hook, the pet and the office server."""
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
