"""Notify the Android ChatBackendService about app and chat state.

The service runs as a plain background start, so a logged-out app is
killable (swipe away closes it). Only an active session is promoted to
foreground. Chat lines produce per-channel alert notifications; the
service drops them while the UI is visible.

On desktop (no Chaquopy/Java runtime) everything is a no-op."""
from __future__ import annotations

# kind -> notification category (chat_defs chat types). Unmapped kinds
# still surface via their channel name, e.g. custom joined channels.
_CHAT_CATEGORIES = {
    "guild": "Guild",
    "officer": "Officer",
    "party": "Party",
    "raid": "Raid",
    "raid_warning": "Raid Warning",
    "whisper": "Whisper",
    "bg": "Battleground",
}
_CHAT_GENERAL = ("say", "yell", "emote")


def _service():
    try:
        from java import jclass
        return jclass("com.mostlynick3.wowchat.ChatBackendService")
    except Exception:
        return None


def set_session_active(active: bool, title: str = "", text: str = "") -> None:
    svc = _service()
    if svc:
        svc.setSessionActive(bool(active), str(title or ""), str(text or ""))


def notify_chat(kind: str, channel: str, sender: str, text: str) -> None:
    """One Android notification category per chat channel."""
    label = _CHAT_CATEGORIES.get(kind)
    if not label and channel:
        label = channel
    if not label and kind in _CHAT_GENERAL:
        label = "General"
    if not label:
        return
    svc = _service()
    if svc:
        svc.postNotification(str(label), str(sender or ""),
                             str(text or ""))
