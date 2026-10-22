"""Smoke test for any OS (CI runs it on Windows, macOS and Linux under xvfb).

  python tests/smoke.py [--shots DIR] [--frozen DIR]

1. the hook: a short session in a throwaway home; checks sessions.json, the status files and a reaction
2. processes: this process in the process table with its parent, pid_alive, the one-pet lock
3. the pet, in this process: every state, reaction, outfit, Lithnode's crab, buddies, his menu;
   fails on any Tk callback error. --shots saves screenshots along the way (Mac and Linux).
--frozen DIR: the built app's folder (on the Mac, "Claude Pet.app/Contents/MacOS"): runs its
   claude-pet-cli as the hook, then starts ClaudePet for a few seconds and checks he's up.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(tempfile.mkdtemp(prefix="claude-pet-smoke-"))
os.environ["HOME"] = os.environ["USERPROFILE"] = str(HOME)   # before shared works out its paths
sys.path.insert(0, str(ROOT))

import shared  # noqa: E402

PY = [sys.executable]
EXE = ".exe" if shared.WINDOWS else ""
failures = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what, flush=True)
    if not ok:
        failures.append(what)


def run_hook(command, event, payload):
    shared.DIR.mkdir(parents=True, exist_ok=True)
    shared.HEARTBEAT.write_text(str(time.time()))   # looks like he's up, so the hook doesn't start one
    env = {**os.environ, "CLAUDE_CODE_ENTRYPOINT": "cli"}
    env.pop("LITHNODE_AGENT", None)
    result = subprocess.run(command + [event], input=json.dumps(payload), text=True,
                            capture_output=True, env=env, timeout=60)
    if result.returncode:
        print(result.stdout, result.stderr)
    return result.returncode == 0


def test_hook(command, label):
    base = {"session_id": f"smoke-{label}", "cwd": str(ROOT), "transcript_path": ""}
    ok = all(run_hook(command, event, {**base, **extra}) for event, extra in (
        ("SessionStart", {}),
        ("UserPromptSubmit", {}),
        ("PreToolUse", {"tool_name": "Edit", "tool_input": {"file_path": "/x/pet.py"}}),
        ("PostToolUse", {"tool_name": "Bash", "tool_input": {"command": "git commit -m hi"}}),
    ))
    check(ok, f"{label}: hook runs every event")
    sessions = json.loads(shared.SESSIONS.read_text())
    entry = sessions.get(f"smoke-{label}", {})
    check(entry.get("project") == ROOT.name and entry.get("tools") == 1, f"{label}: session recorded")
    check(shared.STATUS.read_text() == "working", f"{label}: status file says working")
    check(json.loads(shared.REACT.read_text()).get("kind") == "commit", f"{label}: git commit reaction")
    run_hook(command, "SessionEnd", base)
    check(f"smoke-{label}" not in json.loads(shared.SESSIONS.read_text()), f"{label}: SessionEnd removes it")


def test_processes():
    table = shared.process_table()
    me = os.getpid()
    check(me in table and table[me][0] == os.getppid(), "process table has this process and its parent")
    check("python" in table[me][1], f"process name looks right ({table[me][1]!r})")
    check(shared.pid_alive(me) and not shared.pid_alive(2 ** 22 + 12345), "pid_alive")
    import desktop
    if shared.WINDOWS and not os.environ.get("CI"):
        print("skip one-pet lock (it's per Windows user, and your own pet may hold it)")
    else:
        check(desktop.already_running() is False, "takes the one-pet lock")
    if not shared.WINDOWS:   # a second taker (another process) must see it held
        held = subprocess.run(PY + ["-c", "import sys; sys.path.insert(0, %r); import desktop; "
                                    "print(desktop.already_running())" % str(ROOT)],
                              capture_output=True, text=True, timeout=30).stdout.strip()
        check(held == "True", "a second pet sees the lock held")


def screenshot(path):
    command = (["screencapture", "-x", str(path)] if shared.MAC else
               None if shared.WINDOWS else ["import", "-window", "root", str(path)])
    if command:
        try:
            subprocess.run(command, timeout=20, capture_output=True)
        except (OSError, subprocess.SubprocessError) as error:
            print("no screenshot:", error)


def test_pet(shots):
    import tkinter as tk

    errors = []
    tk.Tk.report_callback_exception = lambda self, *exc: errors.append("".join(traceback.format_exception(*exc)))

    import pet
    import pet_menu

    lith = {"on": False}
    pet.claude_running = lambda: True                 # so the session file below counts
    pet.lithnode_open = lambda: lith["on"]
    pet.open_claude_app = lambda: True               # no browser or app from a test
    if not os.environ.get("CI"):
        pet.focus_session = lambda session: False     # don't shuffle a developer's windows
    shared.write_sessions({"smoke-pet": {"pid": os.getpid(), "ts": time.time(), "status": "working",
                                         "subagents": {"a": {"ts": time.time()}, "b": {"ts": time.time()}}}})
    shared.STATUS.write_text("idle")
    p = pet.Pet()
    shaped = getattr(p.reshape, "shaped", False)
    print("see-through:", "X11 shape" if shaped else "key color / native", flush=True)
    if os.environ.get("SMOKE_EXPECT_SHAPE"):
        check(shaped, "Linux window is shaped")

    def status(state, detail=""):
        shared.STATUS.write_text(state)
        shared.DETAIL.write_text(detail)

    def react(kind):
        shared.REACT.write_text(json.dumps({"kind": kind, "ts": time.time()}))

    def context(fill):
        shared.CONTEXT.write_text(json.dumps({"tokens": int(fill * 200000), "window": 200000}))

    def shot(name):
        if shots:
            p.root.update()
            screenshot(Path(shots) / f"{name}.png")

    class Click:
        x_root, y_root = 400, 300

    steps = [
        (lambda: status("working", "Editing pet.py"), 1.2), (lambda: shot("working"), 0.1),
        (lambda: status("waiting"), 0.8), (lambda: status("celebrate"), 0.8),
        (lambda: react("oops"), 0.8), (lambda: react("push"), 1.0), (lambda: shot("push"), 0.1),
        (lambda: context(0.95), 1.2), (lambda: status("idle"), 0.6),
        (lambda: shared.LIMIT.write_text(json.dumps({"resets_at": time.time() + 3600})), 1.5),
        (lambda: shot("juice"), 0.1), (lambda: shared.LIMIT.unlink(), 0.3),
        (lambda: lith.update(on=True), 1.3), (lambda: status("working", "Crab mode"), 0.6),
        (lambda: shot("crab"), 0.1), (lambda: lith.update(on=False), 1.2),
        *[(lambda name=name: p.set_outfit(name), 0.25) for name in pet_menu.outfits_now()],
        (lambda: p.set_outfit("party hat"), 0.2),
        (lambda: p.show_menu(Click), 0.5), (lambda: shot("menu"), 0.1),
        (lambda: p.menu and p.menu.set_hover("fit:crown"), 0.3), (lambda: p.menu and p.menu.close(), 0.3),
        (lambda: p.clicked(), 1.0),
    ]

    def play(i=0):
        if i == len(steps):
            p.root.after(300, p.quit)
            return
        action, wait = steps[i]
        try:
            action()
        except Exception:
            errors.append(traceback.format_exc())
        p.root.after(int(wait * 1000), play, i + 1)

    p.root.after(800, play)
    p.root.after(60000, p.quit)   # never hang CI
    started = time.time()
    p.run()
    check(time.time() - started < 55, "pet ran the whole script")
    check(p.buddies and len(p.buddies) == 2, "two subagent buddies showed up")
    for error in errors:
        print(error)
    check(not errors, f"no Tk errors ({len(errors)})")


def test_frozen(folder, shots):
    folder = Path(folder)
    cli = [str(folder / f"claude-pet-cli{EXE}"), "hook"]
    test_hook(cli, "frozen")
    out = subprocess.run([cli[0]], capture_output=True, text=True, timeout=60)
    check(out.returncode == 0 and "hook <Event>" in out.stdout, "frozen cli prints its usage")
    shared.HEARTBEAT.unlink(missing_ok=True)
    if shared.WINDOWS:
        proc = subprocess.Popen([str(folder / "ClaudePet.exe"), "--keep"])
    else:
        proc = subprocess.Popen([str(folder / "ClaudePet"), "--keep"])
    time.sleep(8)
    alive = proc.poll() is None
    check(alive, "frozen pet keeps running")
    beat = time.time() - shared.HEARTBEAT.stat().st_mtime if shared.HEARTBEAT.exists() else 99
    check(beat < 3, f"frozen pet writes his heartbeat ({beat:.1f}s old)")
    if not shared.WINDOWS:
        settings = HOME / ".claude" / "settings.json"
        hooks = json.loads(settings.read_text()).get("hooks", {}) if settings.exists() else {}
        check(len(hooks) == 11 and "claude-pet-cli" in json.dumps(hooks), "first start added the 11 hooks")
        login = shared.LAUNCH_AGENT if shared.MAC else shared.AUTOSTART
        check(login.exists(), f"first start set up starting at sign-in ({login.name})")
    if shots:
        screenshot(Path(shots) / "frozen.png")
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots")
    ap.add_argument("--frozen")
    args = ap.parse_args()
    if args.shots:
        Path(args.shots).mkdir(parents=True, exist_ok=True)
    print(f"{sys.platform}, Python {sys.version.split()[0]}, home {HOME}", flush=True)
    if args.frozen:
        test_frozen(args.frozen, args.shots)
    else:
        test_hook(PY + [str(ROOT / "hook.py")], "source")
        test_processes()
        test_pet(args.shots)
    import shutil
    shutil.rmtree(HOME, ignore_errors=True)
    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
