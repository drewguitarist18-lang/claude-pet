"""Claude Office: a live view of every Claude Code session as a little Clawd.

Serves office.html and a JSON feed of the open sessions on localhost only.
The pet starts this in a background thread; you can also run it alone:

    python office.py        # then open http://127.0.0.1:8765
"""
import json
import os
import re
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import shared

HOST, PORT = "127.0.0.1", 8765
URL = f"http://{HOST}:{PORT}"
PAGE = Path(__file__).with_name("office.html")


BOT_STORE = Path(os.environ.get("CLAWD_BOT_HOME") or Path.home() / ".clawd-bot")
BOT_MARKER = "/.clawd-bot/workspaces/"
_bot_cache = {"mtime": None, "bots": {}}


def bot_for(cwd):
    """The Clawd Bot a session belongs to, if it ran in one of its workspace folders.

    Clawd Bot runs every bot chat as a real Claude Code session inside
    ~/.clawd-bot/workspaces/<bot id>, so the folder tells us which bot it was.
    """
    path = re.sub(r"/+", "/", str(cwd or "").replace("\\", "/"))
    marker = BOT_MARKER if BOT_STORE.name == ".clawd-bot" else f"/{BOT_STORE.name}/workspaces/"
    if marker.lower() not in path.lower():
        return None
    bot_id = path[path.lower().index(marker.lower()) + len(marker):].split("/")[0].lower()
    file = BOT_STORE / "bots.json"
    try:
        mtime = file.stat().st_mtime
        if mtime != _bot_cache["mtime"]:
            bots = json.loads(file.read_text(encoding="utf-8")).get("bots", [])
            _bot_cache.update(mtime=mtime, bots={b["id"].lower(): b for b in bots})
    except (OSError, ValueError, KeyError):
        return None
    bot = _bot_cache["bots"].get(bot_id)
    if not bot:
        return None
    return {"id": bot["id"], "name": bot["name"], "shape": bot["shape"], "color": bot["color"]}


def snapshot():
    sessions = []
    for sid, s in shared.live_sessions().items():
        bot = bot_for(s.get("cwd"))
        sessions.append({
            "id": sid,
            "bot": bot,
            "project": (bot or {}).get("name") or s.get("project") or "session",
            "cwd": s.get("cwd", ""),
            "status": s.get("status", "idle"),
            "status_ts": s.get("status_ts", s.get("started", time.time())),
            "detail": s.get("detail", ""),
            "tokens": s.get("tokens", 0),
            "window": s.get("window", 0),
            "tools": s.get("tools", 0),
            "done": s.get("done", 0),
            "started": s.get("started", time.time()),
            "last": s.get("ts", 0),
            "subagents": [
                {
                    "id": k,
                    "type": v.get("type", "agent"),
                    "detail": v.get("detail", ""),
                    "tools": v.get("tools", 0),
                    "started": v.get("ts", time.time()),
                }
                for k, v in (s.get("subagents") or {}).items()
            ],
        })
    sessions.sort(key=lambda s: s["started"])
    return {"now": time.time(), "sessions": sessions}


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/sessions":
            self._send(json.dumps(snapshot()).encode(), "application/json")
        elif path in ("/", "/index.html"):
            self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass  # keep the pet's (windowless) process quiet


def start_server():
    """Serve in a daemon thread. Returns False if the port is already taken."""
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        return False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return True


def open_office():
    webbrowser.open(URL)


if __name__ == "__main__":
    if not start_server():
        print(f"Already running at {URL}")
    else:
        print(f"Claude Office at {URL}  (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
