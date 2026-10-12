"""Clawd, the Claude status pet: a small walking desktop companion.

State comes from ~/.claude-pet/status (written by hook.py):
  idle       wanders, blinks, winks; falls asleep after 5 quiet minutes
  working    types on a little laptop with a speech bubble for the current tool
  waiting    waves and says he needs you
  celebrate  jumps with confetti after a long task finishes

Drag with the left mouse button to put him on any ledge (he patrols that
height). Right-click for the Claude Office view, outfits, sound and quit.
While running, the pet also serves the Claude Office at http://127.0.0.1:8765.
"""
import ctypes
import json
import math
import random
import struct
import sys
import time
import tkinter as tk
from pathlib import Path

import office
import shared
from shared import CONFIG as CONFIG_FILE
from shared import CONTEXT as CONTEXT_FILE
from shared import DETAIL as DETAIL_FILE
from shared import DIR, HEARTBEAT
from shared import STATUS as STATUS_FILE

CELL = 5
COLS, ROWS = 12, 8
W, H = 200, 112
SPRITE_W = COLS * CELL
OX = (W - SPRITE_W) // 2
TRANSPARENT = "#010203"
BODY = "#D97757"
# While Lithnode is open the pet becomes Lithnode's crab: white like its logo, on the same 12x8 grid
# Lithnode draws (static/sprites.js), with a thin dark outline so he shows on light wallpaper.
CRAB_BODY = "#ecebe6"
CRAB_OUTLINE = "#24242a"
CRAB = (
    ".##......##.",
    "#.#......#.#",
    "###......###",
    ".#.######.#.",
    "..########..",
    "..########..",
    "..#.#..#.#..",
    ".##.#..#.##.",
)
EYE = "#000000"
INK = "#1a1b26"
STATES = ("idle", "working", "waiting", "celebrate")
SLEEP_AFTER = 300
CELEBRATE_FOR = 4.0
OUTFITS = ("none", "party hat", "cap", "crown", "glasses", "bow tie")
CONFETTI = ("#f7768e", "#e0af68", "#9ece6a", "#7dcfff", "#bb9af7")


# ---------------------------------------------------------------- state files

def read_state(now):
    try:
        raw = STATUS_FILE.read_text().strip().lower()
        age = now - STATUS_FILE.stat().st_mtime
    except OSError:
        return "idle"
    if raw not in STATES:
        return "idle"
    if raw == "celebrate" and age > CELEBRATE_FOR:
        return "idle"
    if raw == "idle" and age > SLEEP_AFTER:
        return "sleeping"
    return raw


def read_detail():
    try:
        return DETAIL_FILE.read_text().strip()
    except OSError:
        return ""


def load_config():
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        cfg = {}
    outfit = cfg.get("outfit", "none")
    return {
        "outfit": outfit if outfit in OUTFITS else "none",
        "sound": bool(cfg.get("sound", True)),
        "energy_bar": bool(cfg.get("energy_bar", True)),
    }


def read_context_fill():
    """Fraction of the context window in use (0-1), from hook.py's context.json."""
    try:
        data = json.loads(CONTEXT_FILE.read_text())
        return max(0.0, min(1.0, data["tokens"] / data["window"]))
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
        return 0.0


def save_config(cfg):
    """Merge into config.json so settings the menu doesn't own (context_window) survive."""
    try:
        try:
            merged = json.loads(CONFIG_FILE.read_text())
        except (OSError, ValueError):
            merged = {}
        merged.update(cfg)
        CONFIG_FILE.write_text(json.dumps(merged))
    except OSError:
        pass


# ------------------------------------------------------- session / window info

def open_sessions():
    """Live session entries from sessions.json."""
    return list(shared.live_sessions().values())


WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def app_window_visible(pid):
    """True if this process owns a visible (or minimized) top-level window."""
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
    return bool(found)


def lithnode_open():
    """True while the Lithnode app window is open (shown or minimized)."""
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


def pet_visibility():
    """(any session open, should the pet be shown)."""
    sessions = open_sessions()
    if not sessions:
        return False, False
    show = any(not s.get("app") or app_window_visible(s["app"]) for s in sessions)
    return True, show


_instance_lock = None


def already_running():
    """Take a named mutex; True if another pet already holds it."""
    global _instance_lock
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    _instance_lock = k32.CreateMutexW(None, False, "Local\\ClaudePetSingleInstance")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


# ------------------------------------------------------------------------ pet

class Pet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT)
        self.root.configure(bg=TRANSPARENT)
        self.sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.x = float(self.sw - W - 200)
        self.y = float(sh - H - 50)
        self.root.geometry(f"{W}x{H}+{int(self.x)}+{int(self.y)}")

        self.canvas = tk.Canvas(
            self.root, width=W, height=H, bg=TRANSPARENT, highlightthickness=0
        )
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.end_drag)
        self.canvas.bind("<Button-3>", self.show_menu)

        self.cfg = load_config()
        self.build_menu()

        self.context_fill = read_context_fill()
        self.lith = lithnode_open()
        self.shown = True
        self.keep_alive = "--keep" in sys.argv
        self.last_check = 0.0
        self.empty_since = None
        self.dragging = False
        self.direction = random.choice((-1, 1))
        self.walking = True
        self.phase_until = time.time() + random.uniform(2, 5)
        self.t0 = time.time()
        self.tick()

    # menu ------------------------------------------------------------------
    def build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        outfits = tk.Menu(self.menu, tearoff=0)
        self.outfit_var = tk.StringVar(value=self.cfg["outfit"])
        for name in OUTFITS:
            outfits.add_radiobutton(
                label=name.title(), value=name, variable=self.outfit_var,
                command=self.save_menu_choices,
            )
        self.menu.add_command(label="Open Claude Office", command=office.open_office)
        self.menu.add_cascade(label="Outfit", menu=outfits)
        self.sound_var = tk.BooleanVar(value=self.cfg["sound"])
        self.menu.add_checkbutton(
            label="Sound when he needs you", variable=self.sound_var,
            command=self.save_menu_choices,
        )
        self.energy_var = tk.BooleanVar(value=self.cfg["energy_bar"])
        self.menu.add_checkbutton(
            label="Energy bar", variable=self.energy_var,
            command=self.save_menu_choices,
        )
        self.menu.add_separator()
        self.menu.add_command(label="Quit", command=self.root.destroy)

    def save_menu_choices(self):
        self.cfg = {
            "outfit": self.outfit_var.get(),
            "sound": self.sound_var.get(),
            "energy_bar": self.energy_var.get(),
        }
        save_config(self.cfg)

    def show_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # dragging --------------------------------------------------------------
    def start_drag(self, event):
        self.dragging = True
        self.dx, self.dy = event.x, event.y

    def drag(self, event):
        self.x = self.root.winfo_x() + event.x - self.dx
        self.y = self.root.winfo_y() + event.y - self.dy
        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")

    def end_drag(self, event):
        self.dragging = False

    # lifetime --------------------------------------------------------------
    def check_lifetime(self, now):
        """Heartbeat, show/hide with the Claude window, quit when no session."""
        if now - self.last_check < 1:
            return True
        self.last_check = now
        try:
            HEARTBEAT.write_text(str(now))
        except OSError:
            pass
        self.context_fill = read_context_fill()
        self.lith = lithnode_open()
        if self.keep_alive:
            return True
        any_open, show = pet_visibility()
        if any_open:
            self.empty_since = None
            if show and not self.shown:
                self.root.deiconify()
                self.shown = True
            elif not show and self.shown:
                self.root.withdraw()
                self.shown = False
        else:
            self.empty_since = self.empty_since or now
            if now - self.empty_since > 3:
                self.root.destroy()
                return False
        return True

    # energy ----------------------------------------------------------------
    @property
    def tired(self):
        """0 fresh, 1 sleepy, 2 tired, 3 exhausted (by how full the context is)."""
        fill = self.context_fill
        return 3 if fill >= 0.9 else 2 if fill >= 0.75 else 1 if fill >= 0.5 else 0

    # motion ----------------------------------------------------------------
    def update_motion(self, state, now):
        """Return True if he is walking this frame."""
        if self.dragging or state != "idle":
            return False
        if now >= self.phase_until:
            self.walking = not self.walking
            self.phase_until = now + (
                random.uniform(2, 5) if self.walking else random.uniform(2, 6)
            )
            if self.walking and random.random() < 0.4:
                self.direction *= -1
        if not self.walking:
            return False
        self.x += self.direction * 1.5 * (1.0, 0.9, 0.65, 0.4)[self.tired]
        lo, hi = -OX, self.sw - W + OX  # the sprite, not the window, hits the edge
        if self.x < lo:
            self.x, self.direction = lo, 1
        elif self.x > hi:
            self.x, self.direction = hi, -1
        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")
        return True

    def tick(self):
        now = time.time()
        if not self.check_lifetime(now):
            return
        state = read_state(now)
        walking = self.update_motion(state, now)
        self.draw(now - self.t0, state, walking)
        self.root.after(40, self.tick)

    # drawing ---------------------------------------------------------------
    @property
    def body(self):
        return CRAB_BODY if self.lith else BODY

    def px(self, col, row, oy, color=None, w=1, h=1):
        color = color or self.body
        x0 = OX + col * CELL
        y0 = oy + row * CELL
        self.canvas.create_rectangle(
            x0, y0, x0 + w * CELL, y0 + h * CELL, fill=color, outline=color
        )

    def bubble(self, text, oy, accent=None):
        """Pixel-art speech bubble: dark body, notched corners, blocky tail."""
        accent = accent or self.body
        c = self.canvas
        if len(text) > 26:
            text = text[:25] + "…"
        label_y = max(16, oy - 42)  # sit just above his head (and his hat)
        label = c.create_text(
            W / 2, label_y, text=text, font=("Consolas", 9, "bold"), fill="#e8e6f0"
        )
        x0, y0, x1, y1 = c.bbox(label)
        l, t, r, b = x0 - 9, y0 - 4, x1 + 9, y1 + 4
        n = 3  # corner notch size

        def notched(l, t, r, b):
            return [l + n, t, r - n, t, r - n, t + n, r, t + n, r, b - n, r - n, b - n,
                    r - n, b, l + n, b, l + n, b - n, l, b - n, l, t + n, l + n, t + n]

        shapes = [
            c.create_polygon(notched(l - 2, t - 2, r + 2, b + 2), fill=accent, outline=accent),
            c.create_polygon(notched(l, t, r, b), fill="#232433", outline="#232433"),
        ]
        cx = W / 2
        shapes += [
            c.create_rectangle(cx - 6, b, cx + 6, b + 4, fill=accent, outline=accent),
            c.create_rectangle(cx - 4, b + 4, cx + 4, b + 7, fill=accent, outline=accent),
            c.create_rectangle(cx - 2, b + 7, cx + 2, b + 9, fill=accent, outline=accent),
            c.create_rectangle(cx - 4, b - 1, cx + 4, b + 3, fill="#232433", outline="#232433"),
            c.create_rectangle(cx - 2, b + 3, cx + 2, b + 5, fill="#232433", outline="#232433"),
        ]
        for item in reversed(shapes):  # keep creation order, all behind the text
            c.tag_lower(item)
        c.tag_raise(label)

    def draw_outfit_top(self, oy):
        outfit = self.cfg["outfit"]
        if self.lith:
            if outfit == "party hat":
                self.px(4.5, 2, oy, "#bb9af7", w=3)
                self.px(5.25, 1, oy, "#bb9af7", w=1.5)
                self.px(5.5, 0, oy, "#f7768e", w=1)
            elif outfit == "cap":
                self.px(3, 1.6, oy, "#7aa2f7", w=6, h=1.4)
                self.px(8, 2.4, oy, "#5a7fd0", w=2.5, h=0.6)
            elif outfit == "crown":
                self.px(3, 2, oy, "#e0af68", w=6)
                for col in (3, 5.5, 8):
                    self.px(col, 1, oy, "#e0af68")
                self.px(5.5, 2.4, oy, "#f7768e", w=1, h=0.5)
            return
        if outfit == "party hat":
            self.px(4.5, -1, oy, "#bb9af7", w=3)
            self.px(5.25, -2, oy, "#bb9af7", w=1.5)
            self.px(5.5, -3, oy, "#f7768e", w=1)
        elif outfit == "cap":
            self.px(2.5, -1.4, oy, "#7aa2f7", w=7, h=1.4)
            self.px(8.5, -0.4, oy, "#5a7fd0", w=3, h=0.6)
        elif outfit == "crown":
            self.px(2.5, -1, oy, "#e0af68", w=7)
            for col in (2.5, 5.5, 8.5):
                self.px(col, -2, oy, "#e0af68")
            self.px(5.5, -0.6, oy, "#f7768e", w=1, h=0.5)

    def draw_outfit_face(self, oy):
        c = self.canvas
        outfit = self.cfg["outfit"]
        if outfit == "glasses":
            ey = oy + self.eye_row * CELL
            for col in (3, 8):
                x = OX + col * CELL
                c.create_rectangle(x - 3, ey - 3, x + CELL + 3, ey + CELL + 3,
                                   outline=INK, width=2)
            c.create_line(OX + 3 * CELL + CELL + 3, ey + CELL / 2,
                          OX + 8 * CELL - 3, ey + CELL / 2, fill=INK, width=2)
        elif outfit == "bow tie":
            cx, ty = OX + 6 * CELL, oy + (5.8 if self.lith else 5.2) * CELL
            red = "#f7768e"
            c.create_polygon(cx - 14, ty - 6, cx - 14, ty + 6, cx, ty,
                             fill=red, outline=INK)
            c.create_polygon(cx + 14, ty - 6, cx + 14, ty + 6, cx, ty,
                             fill=red, outline=INK)
            c.create_rectangle(cx - 3, ty - 3, cx + 3, ty + 3, fill="#d4382c", outline=INK)

    def draw(self, t, state, walking):
        c = self.canvas
        c.delete("all")
        ground = H - 6

        if walking:
            bob = 1 if int(t * 6) % 2 else 0
        elif state == "waiting":
            bob = round(abs(math.sin(t * 4)) * 3)
        elif state == "celebrate":
            bob = round(abs(math.sin(t * 7)) * 14)
        elif state == "sleeping":
            bob = 1 if math.sin(t * 1.2) > 0.4 else 0
        else:
            bob = 0
        oy = ground - ROWS * CELL - bob
        working = state == "working"

        if state == "celebrate":
            for i in range(16):
                phase = (t * 1.1 + i * 0.37) % 1
                x = W / 2 + (i - 8) * 11 + math.sin(t * 3 + i) * 6
                y = 4 + phase * (ground - 4)
                c.create_rectangle(x - 2, y - 2, x + 2, y + 2,
                                   fill=CONFETTI[i % len(CONFETTI)], outline="")

        if self.lith:
            self.draw_crab(t, state, walking, oy)
        else:
            # Body (cols 2-9, rows 0-5)
            self.px(2, 0, oy, w=8, h=6)

            # Arms: wave when waiting, up when celebrating, type when working
            if working:
                flip = 0.5 if int(t * 8) % 2 else 0
                self.px(0, 3.4 + flip, oy, w=3, h=1.4)
                self.px(9, 3.4 + 0.5 - flip, oy, w=3, h=1.4)
            else:
                arm_row = 2
                if state == "celebrate" or (state == "waiting" and int(t * 4) % 2 == 0):
                    arm_row = 1
                self.px(0, arm_row, oy, w=12, h=2)

            # Legs (rows 6-7): cols 2, 4, 7, 9. Alternate pairs while walking.
            step = int(t * 6) % 2
            for i, col in enumerate((2, 4, 7, 9)):
                drop = 1 if (walking and i % 2 == step) else 0
                self.px(col, 6, oy, h=2 - drop)

        # Eyes (cols 3 and 8; row 1 on Clawd, row 4 on the crab)
        tired = self.tired
        blink = state == "idle" and not walking and (t % 4.5) < 0.15
        wink = state in ("idle", "working") and tired < 2 and (t % 6.5) < 0.4
        yawn = tired >= 2 and state == "idle" and not walking and (t % 22) < 1.6
        shift = 1 if (walking and self.direction > 0) else 0
        lid = (0, 1, 2.5, 3.8)[tired]  # eyelid height in px: heavier as context fills
        for col in (3, 8):
            x0 = OX + col * CELL
            y0 = oy + self.eye_row * CELL
            if state == "sleeping" or blink or yawn or (wink and col == 8):
                self.px(col, self.eye_row + 0.3, oy, color=EYE, h=0.4)
            elif state == "celebrate":
                c.create_line(x0, y0 + CELL, x0 + CELL / 2, y0, x0 + CELL, y0 + CELL,
                              fill=EYE, width=2)
            else:
                x0 += shift if self.direction > 0 else -shift
                c.create_rectangle(x0, y0, x0 + CELL, y0 + CELL, fill=EYE, outline=EYE)
                if lid:
                    c.create_rectangle(x0 - 1, y0 - 1, x0 + CELL + 1, y0 + lid,
                                       fill=self.body, outline=self.body)
        if yawn:
            mouth = self.eye_row + (0.6 if self.lith else 2)
            c.create_rectangle(OX + 5 * CELL, oy + mouth * CELL, OX + 7 * CELL, oy + (mouth + 1.2) * CELL,
                               fill=EYE, outline=EYE)
        if tired == 3 and state != "sleeping":
            sway = math.sin(t * 2) * 1.5
            drop_x = OX + 9.5 * CELL + sway
            c.create_polygon(drop_x, oy - 8, drop_x - 3, oy - 2, drop_x + 3, oy - 2,
                             fill="#7dcfff", outline="#4aa3d8")

        self.draw_outfit_face(oy)
        self.draw_outfit_top(oy)

        if working and self.lith:
            self.px(2.0, 5.0, oy, color="#3b3b44", w=8.0, h=2.4)
            self.px(2.4, 5.3, oy, color="#1f2430", w=7.2, h=1.8)
            for i in range(2):
                width = 2.0 + ((int(t * 3) + i * 3) % 5)
                shade = ("#9ece6a", "#7dcfff", "#e0af68")[(int(t * 3) + i) % 3]
                self.px(2.8, 5.6 + i * 0.8, oy, color=shade, w=width, h=0.4)
            self.px(1.0, 7.3, oy, color="#8a8a92", w=10.0, h=0.7)
        if working:
            if not self.lith:
                self.draw_laptop(t, oy)
            self.bubble(read_detail() or "Working…", oy)
        elif state == "waiting":

            self.bubble("Needs you!", oy, accent="#f7768e")
        elif state == "celebrate":
            self.bubble("All done!", oy, accent="#9ece6a")
        elif state == "sleeping":
            for i in range(3):
                phase = (t * 0.45 + i / 3) % 1
                c.create_text(W / 2 + 24 + phase * 16, oy - 2 - phase * 26, text="z",
                              fill="#7a7f99", font=("Segoe UI", int(8 + phase * 6), "bold"))
        elif tired == 3:
            self.bubble(f"Context {self.context_fill:.0%} full", oy, accent="#e0af68")

        if self.cfg["energy_bar"]:
            self.draw_energy_bar()

    @property
    def eye_row(self):
        return 4 if self.lith else 1

    def draw_laptop(self, t, oy):
        """Clawd's little laptop: dark lid, glowing screen of scrolling code, base."""
        self.px(1.6, 2.3, oy, color="#3b3b44", w=8.8, h=3.5)
        self.px(2.0, 2.7, oy, color="#1f2430", w=8.0, h=2.7)
        for i in range(3):
            width = 2.0 + ((int(t * 3) + i * 3) % 5)
            shade = ("#9ece6a", "#7dcfff", "#e0af68")[(int(t * 3) + i) % 3]
            self.px(2.4, 3.0 + i * 0.8, oy, color=shade, w=width, h=0.4)
        self.px(1.0, 5.8, oy, color="#8a8a92", w=10.0, h=0.7)

    def draw_crab(self, t, state, walking, oy):
        """Lithnode's crab. Claws (rows 0-2) snap in turn when working, both wave when waiting and go up
        to celebrate; the legs (row 7) step in two groups while walking."""
        if state == "working":
            f = int(t * 8) % 2
            lift = {True: f * 0.5, False: (1 - f) * 0.5}
        elif state == "celebrate" or (state == "waiting" and int(t * 4) % 2 == 0):
            lift = {True: 0.6, False: 0.6}
        else:
            lift = {True: 0, False: 0}
        step = int(t * 6) % 2
        cells = []
        for row, line in enumerate(CRAB):
            for col, ch in enumerate(line):
                if ch != "#":
                    continue
                dy = -lift[col < 4] if row < 3 else 0
                if row == 7 and walking and (col in (1, 2, 7)) == bool(step):
                    dy = -0.5
                cells.append((col, row + dy))
        for col, row in cells:
            x0, y0 = OX + col * CELL, oy + row * CELL
            self.canvas.create_rectangle(x0 - 1, y0 - 1, x0 + CELL + 1, y0 + CELL + 1,
                                         fill=CRAB_OUTLINE, outline=CRAB_OUTLINE)
        for col, row in cells:
            self.px(col, row, oy)

    def draw_energy_bar(self):
        """Tiny pixel bar under his feet: full when context is empty."""
        c = self.canvas
        left = OX + 10
        width = SPRITE_W - 20
        energy = 1.0 - self.context_fill
        color = "#9ece6a" if energy > 0.5 else "#e0af68" if energy > 0.25 else "#f7768e"
        top = H - 4
        c.create_rectangle(left - 1, top - 1, left + width + 1, top + 3, fill="#232433", outline="")
        c.create_rectangle(left, top, left + width * energy, top + 2, fill=color, outline="")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if already_running():
        raise SystemExit
    DIR.mkdir(parents=True, exist_ok=True)
    if not STATUS_FILE.exists():
        STATUS_FILE.write_text("idle")
    office.start_server()  # the Claude Office view lives as long as the pet does
    Pet().run()
