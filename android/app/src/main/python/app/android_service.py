"""Tell the Android ChatBackendService whether a world session is active.

The service is a plain background start, so a logged-out app is killable
(swipe away closes it). Only an active session is promoted to foreground.
On desktop (no Chaquopy/Java runtime) this is a no-op."""
from __future__ import annotations


def set_session_active(active: bool, title: str = "", text: str = "") -> None:
    try:
        from java import jclass
        svc = jclass("com.mostlynick3.wowchat.ChatBackendService")
        svc.setSessionActive(bool(active), str(title or ""), str(text or ""))
    except Exception:
        pass
