"""Desktop wrapper: starts the backend and opens a window.

Prefers `pywebview` if installed (native window, good for PyInstaller
executables); otherwise falls back to the default system browser.
Run:  python3 desktop.py
"""
import os
import sys
import threading
import time
import webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from app.server import app, load_defaults  # noqa: E402


def _run_server(host: str, port: int):
    app.run(host=host, port=port, threaded=True, use_reloader=False)


def main():
    cfg = load_defaults()
    host = os.environ.get("YGG_CHAT_HOST", cfg.get("http_host", "127.0.0.1"))
    port = int(os.environ.get("YGG_CHAT_PORT", cfg.get("http_port", 5950)))
    url = f"http://{host}:{port}/"
    t = threading.Thread(target=_run_server, args=(host, port), daemon=True)
    t.start()
    time.sleep(1.2)
    try:
        import webview  # type: ignore
        webview.create_window("WoW Chat Client", url, width=1100, height=750)
        webview.start()
    except ImportError:
        print(f"pywebview not installed; opening system browser at {url}")
        print("Tip: pip install pywebview  (optional, for a native window)")
        _serve_forever_browser(url)
    except Exception as exc:
        # Window backend unusable here (e.g. frozen build without a GUI
        # toolkit, or no display) — degrade to the system browser
        # instead of crashing.
        print(f"native window unavailable ({exc}); "
              f"opening system browser at {url}")
        _serve_forever_browser(url)


def _serve_forever_browser(url: str):
    try:
        webbrowser.open(url)
    except Exception as exc:
        print(f"could not open a browser ({exc}); "
              f"visit {url} manually")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
