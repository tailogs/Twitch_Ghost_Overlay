import sys
import os
import time
import threading
import json

LAUNCHER_STATE_FILE = "launcher_state.json"
HEARTBEAT_FILE = "heartbeat.tmp"

def _log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[LAUNCHER {ts}] {msg}"
    try:
        with open("overlay.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)
    except Exception:
        pass

def _write_state(status: str):
    try:
        with open(LAUNCHER_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "status": status,
                "pid": os.getpid(),
                "ts": time.time(),
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _heartbeat_loop():
    while True:
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(str(time.time()))
        except Exception:
            pass
        time.sleep(5)

def main():
    _log("=== Twitch Ghost Overlay Launcher ===")
    _write_state("running")

    threading.Thread(target=_heartbeat_loop, name="Heartbeat", daemon=True).start()

    try:
        from twitch_overlay import run_overlay
        run_overlay()
        
    except KeyboardInterrupt:
        _log("Выход по клавиатуре")
    except Exception as e:
        _log(f"КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _write_state("stopped")
        try:
            os.remove(HEARTBEAT_FILE)
        except Exception:
            pass
        try:
            os.remove(LAUNCHER_STATE_FILE)
        except Exception:
            pass
        _log("Программа завершена")


if __name__ == "__main__":
    main()