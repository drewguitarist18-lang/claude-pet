"""The pet's desktop side, per OS: whether Claude's window is up, bringing it forward, opening the
Claude app, one pet at a time, see-through windows and fonts.

Windows uses user32 (and a key color for see-through); the Mac uses `open` and Tk's transparent
windows; Linux uses wmctrl or xdotool when installed, and the X11 Shape extension to cut the window
down to what's drawn (Tk has no see-through color there).
"""
import ctypes
import ctypes.util
import os
import struct
import subprocess
import sys
import webbrowser

import shared
from shared import MAC, WINDOWS

if WINDOWS:
    _FONTS, _SCALE = {"ui": "Segoe UI", "ui-bold": "Segoe UI Semibold", "mono": "Consolas"}, 1.0
elif MAC:
    _FONTS, _SCALE = {"ui": "Helvetica Neue", "ui-bold": "Helvetica Neue", "mono": "Menlo"}, 4 / 3  # Tk points are pixels there
else:
    _FONTS, _SCALE = {"ui": "DejaVu Sans", "ui-bold": "DejaVu Sans", "mono": "DejaVu Sans Mono"}, 1.0


def font(kind, size, *style):
    """A Tk font tuple: kind is "ui", "ui-bold" or "mono", size in Windows points."""
    if kind == "ui-bold" and not WINDOWS:
        style = ("bold", *style)
    return (_FONTS[kind], round(size * _SCALE), *style)


# ------------------------------------------------------------- see-through

def see_through(win, canvas, key):
    """Make everything in `key` see-through and click-through. Returns reshape(): call it after
    each redraw (it only does work on Linux, where the window is cut to the canvas's items)."""
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    if WINDOWS:
        win.attributes("-transparentcolor", key)
        win.configure(bg=key)
        canvas.configure(bg=key)
    elif MAC:
        win.attributes("-transparent", True)
        win.configure(bg="systemTransparent")
        canvas.configure(bg="systemTransparent")
    else:
        win.configure(bg=key)
        canvas.configure(bg=key)
        try:
            return _Shaper(win, canvas)
        except (OSError, AttributeError, ValueError):
            pass   # no X11 (or no Shape extension): he gets a dark box instead
    return lambda: None


class _XRect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short),
                ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]


class _Shaper:
    """Sets the window's X11 shape to the union of the canvas items, so the rest is see-through
    and clicks fall through to what's behind."""
    shaped = True

    def __init__(self, win, canvas):
        if not os.environ.get("DISPLAY"):
            raise OSError("no X display")
        x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        self.xext = ctypes.CDLL(ctypes.util.find_library("Xext") or "libXext.so.6")
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XFlush.argtypes = [ctypes.c_void_p]
        self.xext.XShapeQueryExtension.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                                                   ctypes.POINTER(ctypes.c_int)]
        self.xext.XShapeCombineRectangles.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(_XRect), ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.x11, self.canvas, self.win = x11, canvas, win
        self.dpy = x11.XOpenDisplay(None)
        event, error = ctypes.c_int(), ctypes.c_int()
        if not self.dpy or not self.xext.XShapeQueryExtension(self.dpy, event, error):
            raise OSError("no Shape extension")
        win.update_idletasks()
        self.xid = None

    def __call__(self):
        if self.xid is None:
            frame = self.win.wm_frame()
            self.xid = int(frame, 16) if frame else self.win.winfo_id()
        c = self.canvas
        rects = []
        for item in c.find_all():
            kind = c.type(item)
            if kind in ("rectangle", "polygon", "line"):
                xs, ys = c.coords(item)[0::2], c.coords(item)[1::2]
                pad = float(c.itemcget(item, "width") or 0) / 2 if kind == "line" or c.itemcget(item, "fill") == "" else 0
                box = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
            else:
                box = c.bbox(item)
            if not box:
                continue
            x0, y0, x1, y1 = (round(v) for v in box)
            if x1 > x0 and y1 > y0:
                rects.append(_XRect(x0, y0, x1 - x0, y1 - y0))
        array = (_XRect * len(rects))(*rects)
        # ShapeBounding (0) with ShapeSet (0); input follows the bounding shape
        self.xext.XShapeCombineRectangles(self.dpy, self.xid, 0, 0, 0, array, len(rects), 0, 0)
        self.x11.XFlush(self.dpy)


# ------------------------------------------------------------ windows and apps

if WINDOWS:
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def find_window(pid):
    """This process's main top-level window (visible or minimized), or None. Windows only."""
    user32 = ctypes.windll.user32
    found = []

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        rect = ctypes.create_string_buffer(16)
        user32.GetWindowRect(hwnd, rect)
        left, top, right, bottom = struct.unpack("4i", rect.raw)
        if user32.IsIconic(hwnd) or (right - left > 200 and bottom - top > 200):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    return found[0] if found else None


def app_window_visible(pid):
    """True if this process owns a visible (or minimized) top-level window. Outside Windows: if it runs."""
    if WINDOWS:
        return find_window(pid) is not None
    return shared.pid_alive(pid)


def _ancestors(pid, table, steps=12):
    """pid, its parent, grandparent... (as far as the table goes)."""
    for _ in range(steps):
        if not pid:
            return
        yield pid
        pid = table.get(pid, (0, ""))[0]
        if pid not in table:
            return


def focus_session(session):
    """Bring the window this session runs in to the front: the desktop app's, or the terminal
    (or editor) that started the CLI. True if one was found."""
    try:
        table = shared.process_table()
    except Exception:
        table = {}
    chain = [session["app"]] if session.get("app") else []
    chain += list(_ancestors(session.get("pid"), table))
    windows = _linux_windows() if not (WINDOWS or MAC) else None
    for pid in chain:   # the nearest one with a window wins
        if WINDOWS:
            hwnd = find_window(pid)
            if hwnd:
                return bring_to_front(hwnd)
        elif MAC:
            bundle = _app_bundle(pid)
            if bundle:
                return _run(["/usr/bin/open", "-a", bundle])
        else:
            raised = _raise_linux(windows, pid)
            if raised is not None:
                return raised
    return False


def bring_to_front(hwnd):
    """Windows only lets the foreground app hand over focus, and the pet never takes focus, so
    tap Alt first (the usual way around that lock), then restore and raise the window."""
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU down
    user32.keybd_event(0x12, 0, 2, 0)  # and up
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    return user32.GetForegroundWindow() == hwnd


def _app_bundle(pid):
    """Mac: the outermost .app this process lives in (Terminal, iTerm, VS Code, Claude...), or None."""
    path = shared.process_exe(pid)
    return path[:path.index(".app/") + 4] if ".app/" in path else None


def _linux_windows():
    """[(window id, pid)] of the desktop's windows, via wmctrl (or xdotool), [] without either."""
    try:
        out = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True, timeout=3).stdout
        return [(line.split()[0], int(line.split()[2])) for line in out.splitlines()
                if len(line.split()) > 2 and line.split()[2].isdigit()]
    except (OSError, subprocess.SubprocessError):
        return None   # no wmctrl: xdotool looks windows up by pid itself


def _raise_linux(windows, pid):
    """Raise this process's window: True/False for how that went, None if it has none."""
    if windows is not None:
        ids = [wid for wid, owner in windows if owner == pid]
        return _run(["wmctrl", "-ia", ids[0]]) if ids else None
    try:
        out = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)],
                             capture_output=True, text=True, timeout=3).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return _run(["xdotool", "windowactivate", out[-1]]) if out else None


def _run(command):
    try:
        return subprocess.run(command, capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def open_claude_app():
    """Start (or wake) the Claude desktop app; a running copy comes forward. Without one (Linux has
    no desktop app), claude.ai opens in the browser.
    On Windows the app id comes from a running Claude.exe's package folder, else the Store package's usual one."""
    if MAC:
        return _run(["/usr/bin/open", "-a", "Claude"]) or webbrowser.open("https://claude.ai")
    if not WINDOWS:
        return webbrowser.open("https://claude.ai")
    family = "Claude_pzs8sxrjxfjjc"
    try:
        for proc_path in shared.process_paths("claude.exe"):
            parts = proc_path.replace("/", "\\").split("\\")
            if "WindowsApps" in parts:
                package = parts[parts.index("WindowsApps") + 1]   # Claude_<version>_x64__<hash>
                family = package.split("_")[0] + "_" + package.rsplit("__", 1)[-1]
                break
    except Exception:
        pass
    try:
        os.startfile(f"shell:AppsFolder\\{family}!Claude")
        return True
    except OSError:
        return False


def lithnode_open():
    """True while the Lithnode app window is open (shown or minimized). Elsewhere: while it runs."""
    if not WINDOWS:
        try:
            return any(name.startswith("lithnode") for name in shared.process_names())
        except Exception:
            return False
    user32 = ctypes.windll.user32
    found = []

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) != 8:
            return True
        title = ctypes.create_unicode_buffer(16)
        cls = ctypes.create_unicode_buffer(64)
        user32.GetWindowTextW(hwnd, title, 16)
        user32.GetClassNameW(hwnd, cls, 64)
        if title.value == "Lithnode" and cls.value == "Chrome_WidgetWin_1":
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    return bool(found)


_instance_lock = None


def already_running():
    """Take the one-pet lock (a named mutex on Windows, a file lock elsewhere); True if another
    pet already holds it."""
    global _instance_lock
    if WINDOWS:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        _instance_lock = k32.CreateMutexW(None, False, "Local\\ClaudePetSingleInstance")
        return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    import fcntl
    shared.DIR.mkdir(parents=True, exist_ok=True)
    _instance_lock = open(shared.DIR / "pet.lock", "w")
    try:
        fcntl.flock(_instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except OSError:
        return True


def chime():
    """The 'Claude needs you' sound."""
    try:
        if WINDOWS:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return
        for command in ((["afplay", "/System/Library/Sounds/Glass.aiff"],) if MAC else
                        (["canberra-gtk-play", "-i", "message"],
                         ["paplay", "/usr/share/sounds/freedesktop/stereo/message.oga"])):
            try:
                subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except OSError:
                continue
    except Exception:
        pass
