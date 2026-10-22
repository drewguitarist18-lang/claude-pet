"""Clawd, the Claude status pet: a small walking desktop companion.

State comes from ~/.claude-pet/status (written by hook.py):
  idle       wanders, blinks, winks; falls asleep after 5 quiet minutes
  working    types on a little laptop with a speech bubble for the current tool
  waiting    waves and says he needs you
  celebrate  jumps with confetti after a long task finishes
  juice      out of juice: asleep until the usage limit resets (the time is in his bubble)

Reactions: a facepalm when a tool fails, fireworks on a git commit or push. Subagents show up
as tiny buddies beside him. Click him to jump to Claude (the session that needs you first), or
to open the Claude app when no window is up.

"Always on screen" (the default) keeps him up all the time and starts him when you sign in; switched
off, he only shows while Claude is open (the desktop app's window, or a terminal running Claude
Code). Background agents don't count.
Drag with the left mouse button to put him on any ledge (he patrols that
height). Right-click for his menu (pet_menu.py): outfits, sound, the context bar, quit.
"""
import json
import math
import os
import random
import sys
import time
import tkinter as tk
from pathlib import Path

import desktop
import shared
from desktop import app_window_visible, focus_session, lithnode_open, open_claude_app
from pet_menu import CRAB, PetMenu, draw_seasonal, mini_clawd, outfits_now
from shared import CONFIG as CONFIG_FILE
from shared import CONTEXT as CONTEXT_FILE
from shared import DETAIL as DETAIL_FILE
from shared import DIR, HEARTBEAT, LIMIT, REACT
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
EYE = "#000000"
INK = "#1a1b26"
STATES = ("idle", "working", "waiting", "celebrate")
SLEEP_AFTER = 300
CELEBRATE_FOR = 4.0
REACT_FOR = 2.6
PET_FOR = 1.4
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
        "outfit": outfit if outfit in outfits_now() else "none",
        "sound": bool(cfg.get("sound", True)),
        "energy_bar": bool(cfg.get("energy_bar", True)),
        "always_on": bool(cfg.get("always_on", True)),
    }


def read_context_fill():
    """Fraction of the context window in use (0-1), from hook.py's context.json."""
    try:
        data = json.loads(CONTEXT_FILE.read_text())
        return max(0.0, min(1.0, data["tokens"] / data["window"]))
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
        return 0.0


def read_limit():
    """Unix time the usage limit resets, 0 if it isn't hit (hook.py writes limit.json on a failed turn)."""
    try:
        return float(json.loads(LIMIT.read_text()).get("resets_at") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0.0


def back_at(when, now):
    """'8:10pm', or 'Fri 9am' when it's more than a day off."""
    stamp = time.localtime(when)
    clock = time.strftime("%I:%M%p", stamp).lstrip("0").lower().replace(":00", "")
    return clock if when - now < 20 * 3600 else time.strftime("%a ", stamp) + clock


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
    """Live sessions someone is looking at (background agents left out)."""
    return [s for s in shared.live_sessions().values() if not s.get("headless")]


def claude_running():
    """True while any Claude process runs (the desktop app or Claude Code)."""
    try:
        return shared.CLAUDE_EXE in shared.process_names()
    except Exception:
        return True   # can't tell: fall back to the sessions alone


def pet_visibility(sessions):
    """(any session open, should the pet be shown) for these open sessions."""
    if not sessions:
        return False, False
    show = any(not s.get("app") or app_window_visible(s["app"]) for s in sessions)
    return True, show


# ------------------------------------------------------------------------ pet

class Pet:
    def __init__(self):
        self.root = tk.Tk()
        self.canvas = tk.Canvas(
            self.root, width=W, height=H, bg=TRANSPARENT, highlightthickness=0
        )
        self.canvas.pack()
        # borderless before placing him: on the Mac, turning that on afterwards moves the window
        self.reshape = desktop.see_through(self.root, self.canvas, TRANSPARENT)
        self.sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.x = float(self.sw - W - 200)
        self.y = float(sh - H - 50)
        self.root.geometry(f"{W}x{H}+{int(self.x)}+{int(self.y)}")

        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.end_drag)
        self.canvas.bind(desktop.RIGHT_CLICK, self.show_menu)

        self.cfg = load_config()
        self.menu = None

        self.context_fill = read_context_fill()
        self.lith = lithnode_open()
        self.sessions = []
        self.limit_until = self.scanned = self.last_limit_scan = 0.0
        self.react, self.react_seen = None, 0.0   # (kind, start)
        self.petted = 0.0
        self.hearts = []                          # (start, x offset)
        self.buddies = {}                         # id -> {"born", "gone", "slot"}
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
    def show_menu(self, event):
        if self.menu:
            self.menu.close()
            return
        self.menu = PetMenu(self, event.x_root, event.y_root)

    def menu_state(self):
        return self.effective_state(time.time())

    def menu_detail(self):
        now = time.time()
        if self.effective_state(now) == "juice":
            return "back " + back_at(self.limit_until, now)
        return read_detail()

    def effective_state(self, now):
        state = read_state(now)
        if self.limit_until > now and state in ("idle", "sleeping"):
            return "juice"
        return state

    def set_outfit(self, name):
        self.cfg["outfit"] = name
        save_config(self.cfg)

    def toggle_sound(self):
        self.cfg["sound"] = not self.cfg["sound"]
        save_config(self.cfg)

    def toggle_always_on(self):
        self.cfg["always_on"] = not self.cfg["always_on"]
        save_config(self.cfg)
        shared.set_start_at_login(self.cfg["always_on"])

    def toggle_energy_bar(self):
        self.cfg["energy_bar"] = not self.cfg["energy_bar"]
        save_config(self.cfg)

    def quit(self):
        self.root.destroy()

    # dragging --------------------------------------------------------------
    def start_drag(self, event):
        if self.menu:
            self.menu.close()
        self.dragging = True
        self.dx, self.dy = event.x, event.y
        self.press = (event.x_root, event.y_root)

    def drag(self, event):
        self.x = self.root.winfo_x() + event.x - self.dx
        self.y = self.root.winfo_y() + event.y - self.dy
        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")

    def end_drag(self, event):
        self.dragging = False
        px, py = getattr(self, "press", (event.x_root, event.y_root))
        if abs(event.x_root - px) < 4 and abs(event.y_root - py) < 4:
            self.clicked()

    def clicked(self):
        """Jump to Claude: the session waiting on you, else the latest one, else open the app.
        He hops with a few hearts either way."""
        now = time.time()
        order = sorted(self.sessions, key=lambda s: (s.get("status") == "waiting",
                                                     s.get("status_ts", 0), s.get("ts", 0)), reverse=True)
        if not any(focus_session(session) for session in order):
            open_claude_app()
        self.petted = now
        self.hearts = [h for h in self.hearts if now - h[0] < 2]
        self.hearts += [(now + i * 0.22, random.uniform(-24, 24)) for i in range(3)]

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
        self.sessions = open_sessions() if claude_running() else []
        self.check_limit(now)
        self.check_reaction(now)
        self.update_buddies(now)
        if self.keep_alive or self.cfg["always_on"]:
            if not self.shown:
                self.root.deiconify()
                self.shown = True
            return True
        any_open, show = pet_visibility(self.sessions)
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

    def check_limit(self, now):
        """Out of juice until the usage limit resets: from limit.json, and every 15s straight from
        the open sessions' transcripts too (in case the failed turn's hook didn't run)."""
        if now - self.last_limit_scan > 15:
            self.last_limit_scan = now
            self.scanned = 0.0
            for session in self.sessions:
                found = shared.usage_limit(session.get("transcript"))
                if found and found[0]:
                    self.scanned = max(self.scanned, float(found[0]))
        until = max(read_limit(), self.scanned)
        self.limit_until = until if until > now else 0.0

    def check_reaction(self, now):
        try:
            data = json.loads(REACT.read_text())
            kind, ts = data["kind"], float(data["ts"])
        except (OSError, ValueError, KeyError, TypeError):
            return
        if ts <= self.react_seen:
            return
        self.react_seen = ts
        if now - ts > 5:
            return   # stale: it happened before he was running
        if kind == "oops" and self.react and self.react[0] == "oops" and now - self.react[1] < 15:
            return   # one facepalm at a time when lots of tools fail
        self.react = (kind, now)

    def reaction(self, now):
        if self.react and now - self.react[1] < REACT_FOR:
            return self.react[0]
        return None

    def update_buddies(self, now):
        """One tiny buddy per running subagent; ones that finish walk off."""
        live = set()
        for session in self.sessions:
            for agent_id in session.get("subagents") or {}:
                live.add(f"{session.get('started')}:{agent_id}")
        for key in live - set(self.buddies):
            taken = {b["slot"] for b in self.buddies.values()}
            self.buddies[key] = {"born": now, "gone": None,
                                 "slot": next(i for i in range(len(taken) + 1) if i not in taken)}
        for key, buddy in list(self.buddies.items()):
            if key not in live and not buddy["gone"]:
                buddy["gone"] = now
            if buddy["gone"] and now - buddy["gone"] > 2:
                del self.buddies[key]

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
        state = self.effective_state(now)
        if self.reaction(now) or now - self.petted < PET_FOR:
            walking = False
        else:
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
            W / 2, label_y, text=text, font=desktop.font("mono", 9, "bold"), fill="#e8e6f0"
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
        draw_seasonal(lambda col, row, color, w=1, h=1: self.px(col, row, oy, color, w, h),
                      outfit, 3 if self.lith else 0)
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
        now = time.time()
        juice = state == "juice"
        react = self.reaction(now)
        petted = now - self.petted < PET_FOR
        if juice:
            state = "sleeping"
        elif react in ("commit", "push"):
            state = "celebrate"
        elif react == "oops" and state == "working":
            state = "idle"   # put the laptop down to facepalm

        if petted and not juice:
            bob = round(abs(math.sin((now - self.petted) * 9)) * 4)
        elif walking:
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

        if react in ("commit", "push"):
            self.draw_fireworks(now - self.react[1])
        elif state == "celebrate":
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

        self.draw_buddies(now, ground)

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
            elif state == "celebrate" or (petted and not juice):
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
        if react == "oops":
            self.draw_facepalm(oy)
        self.draw_hearts(now, oy)

        if working and self.lith:
            self.px(2.0, 5.0, oy, color="#3b3b44", w=8.0, h=2.4)
            self.px(2.4, 5.3, oy, color="#1f2430", w=7.2, h=1.8)
            for i in range(2):
                width = 2.0 + ((int(t * 3) + i * 3) % 5)
                shade = ("#9ece6a", "#7dcfff", "#e0af68")[(int(t * 3) + i) % 3]
                self.px(2.8, 5.6 + i * 0.8, oy, color=shade, w=width, h=0.4)
            self.px(1.0, 7.3, oy, color="#8a8a92", w=10.0, h=0.7)
        if juice:
            self.bubble("Out of juice · " + back_at(self.limit_until, now), oy, accent="#e0af68")
        elif react == "oops":
            self.bubble("Oops!", oy, accent="#f7768e")
        elif react in ("commit", "push"):
            self.bubble("Committed!" if react == "commit" else "Pushed!", oy, accent="#9ece6a")
        elif working:
            if not self.lith:
                self.draw_laptop(t, oy)
            self.bubble(read_detail() or "Working…", oy)
        elif state == "waiting":

            self.bubble("Needs you!", oy, accent="#f7768e")
        elif state == "celebrate":
            self.bubble("All done!", oy, accent="#9ece6a")
        if state == "sleeping":
            for i in range(3):
                phase = (t * 0.45 + i / 3) % 1
                if getattr(self.reshape, "shaped", False):   # a shaped window shows text as a box
                    self.pixel_z(W / 2 + 24 + phase * 16, oy - 2 - phase * 26, 2 + round(phase * 1.5))
                    continue
                c.create_text(W / 2 + 24 + phase * 16, oy - 2 - phase * 26, text="z",
                              fill="#7a7f99", font=desktop.font("ui", int(8 + phase * 6), "bold"))
        elif tired == 3 and not (react or working or state in ("waiting", "celebrate")):
            self.bubble(f"Context {self.context_fill:.0%} full", oy, accent="#e0af68")

        if self.cfg["energy_bar"]:
            self.draw_energy_bar()
        self.reshape()

    def pixel_z(self, cx, cy, size):
        """A blocky z, 4x4 cells of `size` px, centered at (cx, cy)."""
        x0, y0 = round(cx - 2 * size), round(cy - 2 * size)
        for col, row in ((0, 0), (1, 0), (2, 0), (3, 0), (2, 1), (1, 2), (0, 3), (1, 3), (2, 3), (3, 3)):
            self.canvas.create_rectangle(x0 + col * size, y0 + row * size, x0 + (col + 1) * size,
                                         y0 + (row + 1) * size, fill="#7a7f99", outline="")

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

    def draw_facepalm(self, oy):
        """One arm across his eyes (a claw, on the crab), plus a sweat drop."""
        if self.lith:
            self.px(1.5, 3.4, oy, w=4.2, h=1.4)
        else:
            self.px(0, 2, oy, color=self.body, w=2, h=2)
            self.px(1.6, 0.6, oy, color="#b85f42", w=4.6, h=1.3)
        drop_x = OX + 10 * CELL
        self.canvas.create_polygon(drop_x, oy - 4, drop_x - 3, oy + 2, drop_x + 3, oy + 2,
                                   fill="#7dcfff", outline="#4aa3d8")

    def draw_fireworks(self, age):
        """Three bursts popping one after another above his head."""
        c = self.canvas
        for i, (bx, by) in enumerate(((W / 2 - 62, 34), (W / 2 + 62, 26), (W / 2 + 74, 66))):
            phase = (age - i * 0.35) / 1.1
            if not 0 <= phase <= 1:
                continue
            radius = 3 + phase * 17
            color = CONFETTI[(i * 2) % len(CONFETTI)]
            size = 2.5 * (1 - phase) + 1
            for k in range(10):
                angle = k / 10 * math.tau
                x = bx + math.cos(angle) * radius
                y = by + math.sin(angle) * radius + phase * phase * 8
                c.create_rectangle(x - size, y - size, x + size, y + size, fill=color, outline="")

    def draw_hearts(self, now, oy):
        """Pixel hearts floating up after he's petted."""
        shape = (".##.##.", "#######", ".#####.", "..###..", "...#...")
        for start, dx in self.hearts:
            age = now - start
            if not 0 <= age < 1.3:
                continue
            x0 = W / 2 + dx - 7
            y0 = oy - 18 - age * 28
            for row, line in enumerate(shape):
                for col, ch in enumerate(line):
                    if ch == "#":
                        self.canvas.create_rectangle(x0 + col * 2, y0 + row * 2, x0 + col * 2 + 2,
                                                     y0 + row * 2 + 2, fill="#f7768e", outline="")

    def draw_buddies(self, now, ground):
        """Tiny Clawds (or crabs) for running subagents: two slots each side, a hop when one
        shows up, and a walk off when it's done. More than four shows as +N."""
        c = self.canvas
        offsets = (-50, 50, -78, 78)
        shown = sorted(self.buddies.values(), key=lambda b: b["slot"])
        extra = sum(1 for b in shown if b["slot"] >= len(offsets) and not b["gone"])
        for buddy in shown:
            if buddy["slot"] >= len(offsets):
                continue
            dx = offsets[buddy["slot"]]
            x = W / 2 + dx - 12
            y = ground - 16
            age = now - buddy["born"]
            if age < 0.4:
                y -= math.sin(age / 0.4 * math.pi) * 8
            elif buddy["gone"]:
                gone = now - buddy["gone"]
                x += math.copysign(gone * 60, dx)
                y -= 1 if int(gone * 8) % 2 else 0
            else:
                y -= 1 if int((now + buddy["slot"]) * 4) % 2 else 0
            if -24 < x < W:
                mini_clawd(c, x, y, 2, self.body, "none", crab=self.lith)
        if extra:
            c.create_text(W / 2 + 96, ground - 20, text=f"+{extra}", anchor="e",
                          font=desktop.font("mono", 8, "bold"), fill=self.body)

    def draw_energy_bar(self):
        """Tiny pixel bar under his feet that fills up with the context window."""
        c = self.canvas
        left = OX + 10
        width = SPRITE_W - 20
        used = self.context_fill
        color = "#9ece6a" if used < 0.5 else "#e0af68" if used < 0.75 else "#f7768e"
        top = H - 4
        c.create_rectangle(left - 1, top - 1, left + width + 1, top + 3, fill="#232433", outline="")
        c.create_rectangle(left, top, left + width * used, top + 2, fill=color, outline="")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if desktop.already_running():
        raise SystemExit
    DIR.mkdir(parents=True, exist_ok=True)
    if not STATUS_FILE.exists():
        STATUS_FILE.write_text("idle")
    Pet().run()
