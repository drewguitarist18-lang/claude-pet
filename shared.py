"""State shared by the hook and the pet."""
import contextlib
import ctypes
import json
import os
import subprocess
import sys
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


WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"
CLAUDE_EXE = "claude.exe" if WINDOWS else "claude"   # the CLI's process name (the Mac app's too)


def pid_alive(pid):
    if not WINDOWS:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    k32.GetExitCodeProcess(handle, ctypes.byref(code))
    k32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


_table = (0.0, {}, {})   # (when, table, exe paths): the pet asks a few times a second


def process_table():
    """pid -> (parent pid, exe name) for every running process. Names are lowercase
    ("claude.exe" on Windows, "claude" elsewhere)."""
    return _snapshot()[0]


def process_exe(pid):
    """Full path of this process's executable, or ''."""
    if WINDOWS:
        return _windows_path(pid)
    if MAC:
        return _snapshot()[1].get(pid, "")
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return ""


def _snapshot():
    global _table
    if time.time() - _table[0] < 0.5:
        return _table[1], _table[2]
    table, paths = _windows_table() if WINDOWS else _mac_table() if MAC else _linux_table()
    _table = (time.time(), table, paths)
    return table, paths


def _windows_table():
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
    return table, {}


def _mac_table():
    """From ps: comm is the executable's full path there."""
    out = subprocess.run(["ps", "-axww", "-o", "pid=,ppid=,comm="], capture_output=True,
                         text=True, timeout=5).stdout
    table, paths = {}, {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            pid, path = int(parts[0]), parts[2].strip()
            table[pid] = (int(parts[1]), os.path.basename(path).lower())
            paths[pid] = path
    return table, paths


def _linux_table():
    table = {}
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        try:
            with open(f"/proc/{entry.name}/stat", "rb") as f:
                stat = f.read().decode("utf-8", "replace")
        except OSError:
            continue
        name, rest = stat[stat.index("(") + 1:stat.rindex(")")], stat[stat.rindex(")") + 2:].split()
        table[int(entry.name)] = (int(rest[1]), name.lower())
    return table, {}


def _windows_path(pid):
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    buf = ctypes.create_unicode_buffer(1024)
    size = ctypes.c_ulong(1024)
    ok = k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
    k32.CloseHandle(handle)
    return buf.value if ok else ""


def process_names():
    """Exe names (lowercase) of every running process."""
    return {name for _, name in process_table().values()}


def process_paths(name):
    """Full exe paths of running processes with this exe name (lowercase)."""
    paths = (process_exe(pid) for pid, (_, exe) in process_table().items() if exe == name)
    return [path for path in paths if path]


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "com.claudepet.pet.plist"
AUTOSTART = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart" / "claude-pet.desktop"


def pet_command():
    """How to start the installed pet: the Mac app through `open` (so it runs as an app), else its program."""
    exe = Path(sys.executable)
    if MAC and ".app/" in str(exe):
        return ["/usr/bin/open", "-g", str(exe)[:str(exe).index(".app/") + 4]]
    return [str(exe.with_name("ClaudePet.exe" if WINDOWS else "ClaudePet"))]


def set_start_at_login(on):
    """Start the installed pet when you sign in, or stop doing that: the HKCU Run key on Windows, a
    LaunchAgent on the Mac, an XDG autostart entry on Linux. Source runs are left alone."""
    if not getattr(sys, "frozen", False):
        return
    command = pet_command()
    try:
        if WINDOWS:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                if on:
                    winreg.SetValueEx(key, "Claude Pet", 0, winreg.REG_SZ, f'"{command[0]}"')
                else:
                    try:
                        winreg.DeleteValue(key, "Claude Pet")
                    except FileNotFoundError:
                        pass
        elif MAC:
            if on:
                import plistlib
                LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
                LAUNCH_AGENT.write_bytes(plistlib.dumps(
                    {"Label": "com.claudepet.pet", "ProgramArguments": command, "RunAtLoad": True}))
            else:
                LAUNCH_AGENT.unlink(missing_ok=True)
        elif on:
            AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART.write_text("[Desktop Entry]\nType=Application\nName=Claude Pet\n"
                                 f'Exec="{command[0]}"\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n')
        else:
            AUTOSTART.unlink(missing_ok=True)
    except OSError:
        pass


def live_sessions():
    """{session id: entry} for sessions whose Claude process is still running."""
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
