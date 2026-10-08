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


# Where a Linux WebKitGTK install keeps its helper processes (layout
# varies: Debian/Ubuntu/Mint keep them directly under webkit2gtk-4.x).
# The frozen app cannot spawn its web engine without one of these
# (missing file = instant death of any window); Windows/macOS use
# system WebView2 / WKWebView and need no check.
_WEBKIT_HELPERS = (
    "/usr/lib/x86_64-linux-gnu/webkit2gtk-4.1/WebKitWebProcess",
    "/usr/lib/x86_64-linux-gnu/webkit2gtk-4.0/WebKitWebProcess",
    "/usr/lib/aarch64-linux-gnu/webkit2gtk-4.1/WebKitWebProcess",
    "/usr/lib64/webkit2gtk-4.1/WebKitWebProcess",
    "/usr/lib64/webkit2gtk-4.0/WebKitWebProcess",
    "/usr/libexec/webkit2gtk-4.1/WebKitWebProcess",
    "/usr/libexec/webkit2gtk-4.0/WebKitWebProcess",
    "/usr/lib/webkit2gtk-4.1/WebKitWebProcess",
)


def _have_window_backend() -> bool:
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True
    return any(os.path.exists(p) for p in _WEBKIT_HELPERS)


def main():
    cfg = load_defaults()
    host = os.environ.get("YGG_CHAT_HOST", cfg.get("http_host", "127.0.0.1"))
    port = int(os.environ.get("YGG_CHAT_PORT", cfg.get("http_port", 5950)))
    url = f"http://{host}:{port}/"
    t = threading.Thread(target=_run_server, args=(host, port), daemon=True)
    t.start()
    time.sleep(1.2)
    if not _have_window_backend():
        print("no system web engine found (install libwebkit2gtk for "
              "the app window); opening system browser instead")
        _serve_forever_browser(url)
        return
    try:
        import webview  # type: ignore
    except ImportError:
        print(f"pywebview not installed; opening system browser at {url}")
        print("Tip: pip install pywebview  (optional, for a native window)")
        _serve_forever_browser(url)
        return
    try:
        window = webview.create_window("WoW Chat Client", url,
                                       width=1100, height=750)
    except Exception as exc:
        # Window backend unusable here (e.g. no display) — degrade to
        # the system browser instead of crashing.
        print(f"native window unavailable ({exc}); "
              f"opening system browser at {url}")
        _serve_forever_browser(url)
        return
    state = {"loaded": False, "fell_back": False, "closed": False}
    window.events.loaded += lambda: state.update(loaded=True)
    window.events.closed += lambda: state.update(closed=True)
    watchdog = threading.Thread(target=_watch_window,
                                args=(window, state, url), daemon=True)
    watchdog.start()
    # Blocks on the GTK main loop; returns when the window closes.
    webview.start()
    if state["fell_back"]:
        _serve_forever_browser(url)
    # else: user closed the window -> exit with it.


def _watch_window(window, state: dict, url: str, wait: float = 25.0):
    """Silent-blank safety net: if the window never renders the page
    (dead web process, broken GL, ...), close it and fall back to the
    system browser instead of stranding the user on an empty frame."""
    time.sleep(wait)
    if state["loaded"] or state["closed"]:
        return
    try:
        title = window.evaluate_js("document.title") or ""
    except Exception:
        title = ""
    if title or state["closed"]:
        return  # slow but alive (or already gone); leave it alone
    print("window did not render; falling back to system browser")
    state["fell_back"] = True
    try:
        window.destroy()
    except Exception:
        pass


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
