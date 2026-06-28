import subprocess
import sys
import os
import time
import threading
import ctypes
from ctypes import wintypes
import json

APP_STATE_FILE   = "app_state.json"
SUPERVISOR_STATE = "supervisor_state.json"
HEARTBEAT_FILE   = "heartbeat.tmp"

HOTKEY_VK  = 0x77
HOTKEY_MOD = 0
HOTKEY_ID  = 1
WM_HOTKEY  = 0x0312

CRASH_THRESHOLD = 5.0
CRASH_BACKOFF   = 3.0
MAX_CRASHES     = 20
WATCHDOG_TIMEOUT = 60

CHILD_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "twitch_overlay.pyw"
)

_child_proc   = None
_child_lock   = threading.Lock()
_restart_flag = threading.Event()
_quit_flag    = threading.Event()
_crash_count  = 0


def _log(msg):
    ts   = time.strftime("%H:%M:%S")
    line = f"[SUPERVISOR {ts}] {msg}"
    try:
        log_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "supervisor.log"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _get_channel():
    try:
        with open(APP_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("last_channel", "")
    except Exception:
        return ""


def _write_supervisor_state(status: str):
    try:
        with open(SUPERVISOR_STATE, "w", encoding="utf-8") as f:
            json.dump({
                "status":      status,
                "pid":         os.getpid(),
                "crash_count": _crash_count,
                "ts":          time.time(),
            }, f)
    except Exception:
        pass


def _kill_child():
    global _child_proc
    with _child_lock:
        proc        = _child_proc
        _child_proc = None

    if proc is None:
        return

    _log(f"Killing child PID={proc.pid}")
    try:
        subprocess.call(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=3)
    except Exception:
        pass


def _start_child(channel: str = "") -> subprocess.Popen:
    python_exe = sys.executable
    if python_exe.endswith("python.exe"):
        pythonw = python_exe.replace("python.exe", "pythonw.exe")
        if os.path.exists(pythonw):
            python_exe = pythonw

    cmd = [python_exe, CHILD_SCRIPT]
    if channel:
        cmd.append(channel)
    cmd += ["--supervisor-pid", str(os.getpid())]

    _log(f"Starting child: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    _log(f"Child started PID={proc.pid}")
    return proc


def _read_heartbeat() -> float:
    try:
        with open(HEARTBEAT_FILE, "r") as f:
            return float(f.read().strip())
    except Exception:
        return 0.0


def _watchdog_loop():
    time.sleep(20)

    while not _quit_flag.is_set():
        time.sleep(10)
        if _quit_flag.is_set():
            break

        with _child_lock:
            proc = _child_proc

        if proc is None:
            continue

        if proc.poll() is not None:
            continue

        hb = _read_heartbeat()
        if hb == 0:
            continue

        elapsed = time.time() - hb
        if elapsed > WATCHDOG_TIMEOUT:
            _log(f"Watchdog: heartbeat не обновлялся {elapsed:.0f}s → перезапуск")
            _restart_flag.set()


def _hotkey_loop():
    user32 = ctypes.windll.user32
    ok     = user32.RegisterHotKey(None, HOTKEY_ID, HOTKEY_MOD, HOTKEY_VK)

    if ok:
        _log("F8 registered")
    else:
        err = ctypes.get_last_error()
        _log(f"WARNING: F8 registration failed (WinError {err})")

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd",    wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam",  wintypes.WPARAM),
            ("lParam",  wintypes.LPARAM),
            ("time",    wintypes.DWORD),
            ("pt",      wintypes.POINT),
        ]

    msg = MSG()
    try:
        while not _quit_flag.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    _log("F8 → restart child")
                    _restart_flag.set()
            time.sleep(0.05)
    finally:
        if ok:
            user32.UnregisterHotKey(None, HOTKEY_ID)


def supervisor_main():
    global _child_proc, _crash_count

    _log("Supervisor starting")
    _log(f"Child: {CHILD_SCRIPT}")

    threading.Thread(target=_hotkey_loop,   name="HotkeyLoop",   daemon=True).start()
    threading.Thread(target=_watchdog_loop, name="WatchdogLoop", daemon=True).start()

    channel = _get_channel()

    try:
        while not _quit_flag.is_set():
            _write_supervisor_state("running")
            start_time = time.time()

            with _child_lock:
                _child_proc = _start_child(channel)

            proc = _child_proc

            while not _quit_flag.is_set():
                try:
                    proc.wait(timeout=0.3)
                    break
                except subprocess.TimeoutExpired:
                    pass

                if _restart_flag.is_set():
                    _restart_flag.clear()
                    _log("Restart → killing child")
                    _kill_child()
                    channel = _get_channel()
                    break

            if _quit_flag.is_set():
                _kill_child()
                break

            exit_code = proc.poll()
            uptime    = time.time() - start_time

            if exit_code == 0:
                _log(f"Child exited cleanly (uptime={uptime:.1f}s) → выходим")
                _quit_flag.set()
                break

            _log(f"Child exited code={exit_code} uptime={uptime:.1f}s")

            if uptime < CRASH_THRESHOLD:
                _crash_count += 1
                _log(f"Fast crash #{_crash_count}/{MAX_CRASHES}")
                if _crash_count >= MAX_CRASHES:
                    _log("Too many crashes → giving up")
                    _write_supervisor_state("too_many_crashes")
                    break
                _write_supervisor_state("backoff")
                time.sleep(CRASH_BACKOFF)
            else:
                _crash_count = 0

            channel = _get_channel()
            _log(f"Restarting (channel={channel!r})")

    except KeyboardInterrupt:
        _log("KeyboardInterrupt → shutdown")
    finally:
        _quit_flag.set()
        _kill_child()
        _write_supervisor_state("stopped")
        try:
            os.remove(HEARTBEAT_FILE)
        except Exception:
            pass
        _log("Supervisor stopped")


if __name__ == "__main__":
    supervisor_main()