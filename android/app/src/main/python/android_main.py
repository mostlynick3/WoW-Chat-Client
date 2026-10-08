"""Android entry point (Chaquopy): runs the same Flask backend the
desktop client uses, on localhost. Started once from MainActivity on a
background thread — app.run() blocks, so never call this on the UI
thread."""
import os

from app.server import app, load_defaults


def start():
    cfg = load_defaults()
    port = int(os.environ.get("YGG_CHAT_PORT", cfg.get("http_port", 5950)))
    app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)
