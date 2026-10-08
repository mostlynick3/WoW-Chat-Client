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
    print(f"ygg-chat-client on http://{host}:{port}")
    app.run(host=host, port=port, threaded=True)
