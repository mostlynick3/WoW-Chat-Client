"""Entry point: local web app. Run:  python3 run.py  -> http://127.0.0.1:5950"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from app.server import app, load_defaults  # noqa: E402

if __name__ == "__main__":
    cfg = load_defaults()
    host = os.environ.get("YGG_CHAT_HOST", cfg.get("http_host", "127.0.0.1"))
    port = int(os.environ.get("YGG_CHAT_PORT",
                              cfg.get("http_port", 5950)))
    # Auto-reload on code changes (restarts the process when any .py file
    # under the project changes). Disable with YGG_RELOAD=0, e.g. to keep
    # a connection alive across edits.
    reload = os.environ.get("YGG_RELOAD", "1") != "0"
    print(f"ygg-chat-client on http://{host}:{port}"
          + (" (auto-reload on)" if reload else ""))
    app.run(host=host, port=port, threaded=True, use_reloader=reload)
