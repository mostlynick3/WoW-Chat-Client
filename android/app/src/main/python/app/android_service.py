"""Notify ChatBackendService of session state; no-op without Java.

Logged-out apps stay closable; only an active session is foreground."""
from __future__ import annotations


def set_session_active(active: bool, title: str = "", text: str = "") -> None:
    try:
        from java import jclass
        svc = jclass("com.mostlynick3.wowchat.ChatBackendService")
        svc.setSessionActive(bool(active), str(title or ""), str(text or ""))
    except Exception:
        pass
