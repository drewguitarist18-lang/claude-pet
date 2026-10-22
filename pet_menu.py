"""Clawd's right-click menu: a small dark panel with pixel-notched corners (like his speech
bubble), a status header, today's stats, outfit tiles that preview each outfit on a mini Clawd
(seasonal ones join in October and December), and switches.
Everything is drawn on one canvas; the window's key color makes the corners see-through.
"""
import datetime
import json
import tkinter as tk
import tkinter.font as tkfont

from shared import TODAY

KEY = "#010203"
PANEL, EDGE, HOVER, TILE = "#1b1a22", "#34323f", "#272632", "#23222c"
INK, MUTED, DIM = "#ecebf2", "#9a96aa", "#5d5a6b"
RED = "#f7768e"
# Lithnode's crab on the same 12x8 grid as Clawd (pet.py draws it too)
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
W, PAD, NOTCH = 268, 14, 4
FONT, BOLD, SMALL = ("Segoe UI", 9), ("Segoe UI Semibold", 10), ("Consolas", 7, "bold")
LABELS = {"none": "None", "party hat": "Party hat", "cap": "Cap", "crown": "Crown",
          "glasses": "Glasses", "bow tie": "Bow tie",
          "witch hat": "Witch hat", "pumpkin": "Pumpkin", "santa hat": "Santa hat"}
OUTFITS = ("none", "party hat", "cap", "crown", "glasses", "bow tie")
SEASONAL = {"witch hat": ((10, 1), (11, 2)), "pumpkin": ((10, 1), (11, 2)),
            "santa hat": ((12, 1), (12, 31))}   # (month, day) first and last
STATUS = {"idle": ("Hanging out", "#b8b3c6"), "working": ("Working", "#7dcfff"),
          "waiting": ("Needs you", RED), "celebrate": ("All done", "#9ece6a"),
          "sleeping": ("Asleep", "#7a7f99"), "juice": ("Out of juice", "#e0af68")}


def outfits_now(today=None):
    """The regular outfits plus whichever seasonal ones are in season today."""
    today = today or datetime.date.today()
    md = (today.month, today.day)
    return OUTFITS + tuple(name for name, (first, last) in SEASONAL.items() if first <= md <= last)


def draw_seasonal(px, outfit, top):
    """Seasonal hats with px(col, row, color, w, h) on the 12-col grid; `top` is the head's top row."""
    if outfit == "witch hat":
        px(1.5, top - 0.8, "#3d2a5c", 9, 0.8)
        px(3.5, top - 2, "#3d2a5c", 5, 1.2)
        px(3.5, top - 1.6, "#e0af68", 5, 0.4)
        px(4.5, top - 3, "#3d2a5c", 3, 1)
        px(5.5, top - 3.8, "#3d2a5c", 2, 0.8)
        px(7.2, top - 4.3, "#3d2a5c", 1.2, 0.6)
    elif outfit == "pumpkin":
        px(4, top - 2.2, "#ff9e3b", 4, 2.2)
        px(3.6, top - 1.8, "#ff9e3b", 4.8, 1.4)
        px(5.6, top - 2.2, "#d9771f", 0.8, 2.2)
        px(5.6, top - 3, "#5b8c3a", 0.8, 0.8)
        px(6.4, top - 3, "#5b8c3a", 0.8, 0.4)
    elif outfit == "santa hat":
        px(2.5, top - 1, "#f4f4f4", 7, 1)
        px(3, top - 2, "#e0453a", 6, 1)
        px(4.5, top - 3, "#e0453a", 4, 1)
        px(7.5, top - 3.6, "#e0453a", 1.5, 0.8)
        px(9, top - 3.9, "#f4f4f4", 1.2, 1.2)


def today_stats():
    """'3 sessions · 142 tools · 1h 12m' from hook.py's today.json, or '' before anything ran today."""
    try:
        stats = json.loads(TODAY.read_text())
    except (OSError, ValueError):
        return ""
    if stats.get("date") != datetime.date.today().isoformat():
        return ""
    sessions, tools, minutes = len(stats.get("sessions", [])), stats.get("tools", 0), int(stats.get("work", 0) // 60)
    worked = f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"
    return (f"{sessions} session{'s' * (sessions != 1)} · {tools} tool{'s' * (tools != 1)}"
            f" · {worked}")


def notched(l, t, r, b, n=NOTCH):
    return [l + n, t, r - n, t, r - n, t + n, r, t + n, r, b - n, r - n, b - n,
            r - n, b, l + n, b, l + n, b - n, l, b - n, l, t + n, l + n, t + n]


def mini_clawd(c, x, y, cell, body, outfit, crab=False):
    """Clawd (or Lithnode's crab) at cell size, top-left at (x, y), wearing `outfit`."""
    def px(col, row, color=body, w=1, h=1):
        c.create_rectangle(x + col * cell, y + row * cell, x + (col + w) * cell, y + (row + h) * cell,
                           fill=color, outline="")
    if crab:
        for row, line in enumerate(CRAB):
            for col, ch in enumerate(line):
                if ch == "#":
                    px(col, row)
        eye_row = 4
    else:
        px(2, 0, w=8, h=6)
        px(0, 2, w=12, h=2)
        for col in (2, 4, 7, 9):
            px(col, 6, h=2)
        eye_row = 1
    for col in (3, 8):
        px(col, eye_row, "#000000")
    top = 3 if crab else 0   # where the head starts
    draw_seasonal(lambda col, row, color, w=1, h=1: px(col, row, color, w, h), outfit, top)
    if outfit == "party hat":
        px(4.5, top - 1, "#bb9af7", w=3); px(5.25, top - 2, "#bb9af7", w=1.5); px(5.5, top - 3, RED)
    elif outfit == "cap":
        px(2.5, top - 1.4, "#7aa2f7", w=7, h=1.4); px(8.5, top - 0.4, "#5a7fd0", w=3, h=0.6)
    elif outfit == "crown":
        px(2.5, top - 1, "#e0af68", w=7)
        for col in (2.5, 5.5, 8.5):
            px(col, top - 2, "#e0af68")
    elif outfit == "glasses":
        for col in (3, 8):
            c.create_rectangle(x + (col - .5) * cell, y + (eye_row - .5) * cell, x + (col + 1.5) * cell,
                               y + (eye_row + 1.5) * cell, outline="#1a1b26", width=1)
        px(4.5, eye_row + .4, "#1a1b26", w=3, h=.25)
    elif outfit == "bow tie":
        px(4.6, (5.8 if crab else 5.2) - .6, RED, w=1.2, h=1.2)
        px(6.2, (5.8 if crab else 5.2) - .6, RED, w=1.2, h=1.2)
        px(5.7, (5.8 if crab else 5.2) - .35, "#d4382c", w=.6, h=.7)


class PetMenu:
    def __init__(self, pet, x, y):
        self.pet = pet
        self.win = tk.Toplevel(pet.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", KEY)
        self.win.configure(bg=KEY)
        self.c = tk.Canvas(self.win, width=W, height=10, bg=KEY, highlightthickness=0)
        self.c.pack()
        self.hover = None
        self.items = []   # (key, l, t, r, b, action)
        self.draw()
        h = int(self.c["height"])
        sw, sh = pet.root.winfo_screenwidth(), pet.root.winfo_screenheight()
        x = min(max(4, x - 8), sw - W - 4)
        y = y - h - 8 if y + h + 8 > sh - 48 else y + 8   # open upward near the taskbar
        self.win.geometry(f"{W}x{h}+{x}+{max(4, y)}")
        self.c.bind("<Motion>", self.motion)
        self.c.bind("<Leave>", lambda e: self.set_hover(None))
        self.c.bind("<ButtonRelease-1>", self.click)
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.bind("<FocusOut>", lambda e: self.win.after(1, self.check_focus))
        self.win.focus_force()

    # ---- drawing ------------------------------------------------------------
    def draw(self):
        c, p = self.c, self.pet
        c.delete("all")
        self.items = []
        accent = p.body
        y = PAD

        # header: mini Clawd, name, status, context meter
        mini_clawd(c, PAD, y + 8, 3, accent, p.cfg["outfit"], crab=p.lith)
        state = p.menu_state()
        label, dot = STATUS.get(state, STATUS["idle"])
        detail = p.menu_detail() if state in ("working", "juice") else ""
        c.create_text(PAD + 48, y + 9, text="Lithnode crab" if p.lith else "Clawd", anchor="w", font=BOLD, fill=INK)
        c.create_rectangle(PAD + 48, y + 25, PAD + 54, y + 31, fill=dot, outline="")
        status = label + (f" · {detail}" if detail else "")
        room = W - PAD - 46 - (PAD + 60)   # up to the context meter
        font = tkfont.Font(family=FONT[0], size=FONT[1])
        while font.measure(status) > room and len(status) > 4:
            status = status[:-2].rstrip() + "…"
        c.create_text(PAD + 60, y + 28, text=status, anchor="w", font=FONT, fill=MUTED)
        used = p.context_fill
        tone = "#9ece6a" if used < .5 else "#e0af68" if used < .75 else RED
        c.create_text(W - PAD - 30, y + 12, text="CONTEXT", anchor="e", font=SMALL, fill=DIM)
        c.create_text(W - PAD, y + 12, text=f"{used:.0%}", anchor="e", font=SMALL, fill=tone)
        c.create_rectangle(W - PAD - 34, y + 22, W - PAD, y + 25, fill=TILE, outline="")
        c.create_rectangle(W - PAD - 34, y + 22, W - PAD - 34 + 34 * used, y + 25, fill=tone, outline="")
        y += 48
        y = self.divider(y)

        # today
        stats = today_stats()
        if stats:
            c.create_text(PAD, y + 7, text="TODAY", anchor="w", font=SMALL, fill=DIM)
            c.create_text(PAD + 44, y + 7, text=stats, anchor="w", font=FONT, fill=MUTED)
            y += 16
            y = self.divider(y)

        # outfits
        c.create_text(PAD, y + 6, text="OUTFIT", anchor="w", font=SMALL, fill=DIM)
        shown = LABELS.get(self.hover[4:] if self.hover and self.hover.startswith("fit:") else p.cfg["outfit"], "")
        c.create_text(W - PAD, y + 6, text=shown, anchor="e", font=SMALL, fill=MUTED)
        y += 16
        names = outfits_now()
        gap = 4 if len(names) < 8 else 3
        tw = (W - 2 * PAD - (len(names) - 1) * gap) / len(names)
        th = 36
        for i, name in enumerate(names):
            l = PAD + i * (tw + gap)
            key = f"fit:{name}"
            on = name == p.cfg["outfit"]
            fill = HOVER if key == self.hover else TILE
            c.create_polygon(notched(l, y, l + tw, y + th, 3), fill=accent if on else fill, outline="")
            if on:
                c.create_polygon(notched(l + 2, y + 2, l + tw - 2, y + th - 2, 2), fill=fill, outline="")
            mini_clawd(c, l + (tw - 24) / 2, y + 12, 2, accent, name, crab=p.lith)
            self.items.append((key, l, y, l + tw, y + th, lambda n=name: p.set_outfit(n)))
        y += th + 10
        y = self.divider(y)

        # switches
        for key, text, value, action in (
            ("sound", "Chime when he needs you", p.cfg["sound"], p.toggle_sound),
            ("energy", "Context bar", p.cfg["energy_bar"], p.toggle_energy_bar),
        ):
            y = self.row(y, key, text, action, switch=value)
        y = self.divider(y)
        y = self.row(y, "quit", "Quit Clawd", p.quit, danger=True)
        y += PAD - 6

        h = y
        c.configure(height=h)
        c.create_polygon(notched(0, 0, W - 1, h - 1), fill=EDGE, outline="")
        c.create_polygon(notched(1, 1, W - 2, h - 2), fill=PANEL, outline="")
        c.tag_lower(c.find_all()[-1])
        c.tag_lower(c.find_all()[-1])

    def divider(self, y):
        self.c.create_rectangle(PAD - 4, y + 5, W - PAD + 4, y + 6, fill=EDGE, outline="")
        return y + 12

    def row(self, y, key, text, action, switch=None, danger=False):
        c, h = self.c, 30
        hot = key == self.hover
        if hot:
            c.create_polygon(notched(PAD - 6, y, W - PAD + 6, y + h, 3), fill=HOVER, outline="")
        c.create_text(PAD, y + h / 2, text=text, anchor="w", font=FONT,
                      fill=(RED if danger and hot else INK))
        if switch is not None:
            r, top = W - PAD, y + h / 2 - 7
            c.create_polygon(notched(r - 26, top, r, top + 14, 3), fill=self.pet.body if switch else EDGE, outline="")
            knob = r - 12 if switch else r - 24
            c.create_polygon(notched(knob, top + 2, knob + 10, top + 12, 2), fill=INK if switch else MUTED, outline="")
        self.items.append((key, PAD - 6, y, W - PAD + 6, y + h, action))
        return y + h

    # ---- input --------------------------------------------------------------
    def hit(self, x, y):
        for key, l, t, r, b, action in self.items:
            if l <= x <= r and t <= y <= b:
                return key, action
        return None, None

    def set_hover(self, key):
        if key != self.hover:
            self.hover = key
            self.draw()
            self.c.configure(cursor="hand2" if key else "")

    def motion(self, e):
        self.set_hover(self.hit(e.x, e.y)[0])

    def click(self, e):
        key, action = self.hit(e.x, e.y)
        if not action:
            return
        if key == "quit":
            self.close()
            action()
            return
        action()
        self.draw()

    def check_focus(self):
        try:
            if self.win.focus_displayof() is None:
                self.close()
        except (tk.TclError, KeyError):
            self.close()

    def close(self):
        if self.pet.menu is self:
            self.pet.menu = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass
