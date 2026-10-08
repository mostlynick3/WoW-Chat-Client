"""High-level WoW connection manager (thread-safe, UI-friendly).

Owns AuthClient + WorldClient, background pollers (ping every 30s,
event drain), message history buffer, connection state machine:

  offline -> auth -> world -> chars -> online -> offline

All blocking network errors surface as status dicts; passwords and
session keys are zeroed on disconnect.
"""
from __future__ import annotations

import queue
import threading
import time

from wow.auth_socket import AuthClient
from wow.chat_defs import SENDABLE
from wow.world_socket import ChatLine, WorldClient


class WoWChatManager:
    def __init__(self, history_limit: int = 500):
        self._lock = threading.Lock()
        self.state = "offline"
        self.status = "idle"
        self.account = ""
        self.realm_name = ""
        self.character = ""
        self.auth: AuthClient | None = None
        self.world: WorldClient | None = None
        self.history: list[dict] = []
        self.history_limit = history_limit
        self._seq = 0
        self._ping_thread: threading.Thread | None = None
        self._drain_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.realms: list[dict] = []

    # -- helpers ------------------------------------------------------
    def _push_line(self, line: ChatLine):
        with self._lock:
            self._seq += 1
            self.history.append({
                "id": self._seq, "ts": line.ts, "kind": line.kind,
                "ctype": line.ctype, "sender": line.sender,
                "channel": line.channel, "text": line.text,
                "lang": line.lang,
            })
            if len(self.history) > self.history_limit:
                del self.history[: len(self.history) - self.history_limit]

    def _note(self, text: str, kind: str = "system"):
        with self._lock:
            self._seq += 1
            self.history.append({
                "id": self._seq, "ts": time.time(), "kind": kind,
                "ctype": 0, "sender": "", "channel": "", "text": text,
                "lang": 0,
            })

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self.state, "status": self.status,
                "account": self.account, "realm": self.realm_name,
                "character": self.character,
            }

    # -- lifecycle ----------------------------------------------------
    def login(self, auth_host: str, auth_port: int, username: str,
              password: str, realm_id: int,
              world_host_override: str = "",
              world_port_override: int = 0,
              character_name: str = "") -> dict:
        self.disconnect(silent=True)
        self._stop.clear()
        self.state = "auth"
        self.account = username
        self.status = f"authenticating {username}@{auth_host}:{auth_port} ..."
        try:
            auth = AuthClient(auth_host, int(auth_port))
            auth.logon(username, password)
            self.auth = auth
            realms = auth.realm_list()
            self.realms = [{"id": r.id, "name": r.name, "address": r.address}
                           for r in realms]
            target = next((r for r in realms if r.id == int(realm_id)), None)
            if target is None:
                if realms:
                    target = realms[0]
                else:
                    raise ConnectionError("server returned no realms")
            host, _, port_s = target.address.partition(":")
            port = int(port_s or 8085)
            if world_host_override:
                host = world_host_override
            if world_port_override:
                port = int(world_port_override)
            self.realm_name = f"{target.name} ({host}:{port})"
            self.status = f"world login {host}:{port} ..."
            self.state = "world"
            world = WorldClient()
            assert auth.session_key is not None
            world.connect(host, port)
            world.login(username.upper(), auth.session_key, target.id)
            self.world = world
            chars = [{"guid": c.guid, "name": c.name, "level": c.level}
                     for c in world.characters]
            if not chars:
                raise ConnectionError("no characters on this realm/account")
            pick = character_name or chars[0]["name"]
            entry = next((c for c in chars if c["name"].lower() == pick.lower()),
                         None)
            if entry is None:
                raise ConnectionError(
                    f"character '{pick}' not found. Available: "
                    + ", ".join(c["name"] for c in chars))
            self.status = f"entering world as {entry['name']} ..."
            world.player_login(entry["guid"])
            self.character = entry["name"]
            self.state = "online"
            self.status = f"online as {self.character}"
            self._note(f"Logged in as {self.character} on {self.realm_name}. "
                       f"Say/Yell are proximity-based; join World channel with "
                       f"/join World if your server has one.")
            # background loops
            self._ping_thread = threading.Thread(target=self._ping_loop,
                                                 daemon=True)
            self._drain_thread = threading.Thread(target=self._drain_loop,
                                                  daemon=True)
            self._ping_thread.start()
            self._drain_thread.start()
            return {"ok": True, "character": self.character,
                    "realm": self.realm_name,
                    "characters": [c["name"] for c in chars]}
        except Exception as exc:
            self.status = f"error: {exc}"
            self.state = "offline"
            self._cleanup_nets()
            return {"ok": False, "error": str(exc)}

    def _ping_loop(self):
        while not self._stop.is_set():
            for _ in range(60):
                if self._stop.is_set():
                    return
                time.sleep(0.5)
            try:
                if self.world:
                    self.world.ping()
            except Exception:
                self._note("ping failed; connection may be dead.", "system")
                return

    def _drain_loop(self):
        assert self.world
        w = self.world
        while not self._stop.is_set():
            try:
                try:
                    line = w.inbox.get(timeout=0.5)
                    self._push_line(line)
                    continue
                except queue.Empty:
                    pass
                try:
                    ev = w.events.get(timeout=0.1)
                except queue.Empty:
                    continue
                t = ev.get("t")
                if t == "disconnect":
                    self.status = "disconnected by server"
                    self.state = "offline"
                    self._note("Disconnected by server.", "system")
                    return
                elif t == "channel_notify":
                    pass  # already surfaced as notice line
                elif t == "who":
                    self._note(_fmt_who(ev.get("detail", {})), "roster")
                elif t == "channel_list":
                    self._note(_fmt_chan_list(ev.get("detail", {})), "roster")
                elif t == "login_verify":
                    pass
                elif t == "parse_error":
                    pass
            except Exception:
                time.sleep(0.5)

    # -- actions ------------------------------------------------------
    def send(self, kind: str, text: str, target: str = "",
             channel: str = "", lang: int = 7) -> dict:
        if self.state != "online" or not self.world:
            return {"ok": False, "error": "not online"}
        ctype = int(SENDABLE.get(kind, SENDABLE["say"]))
        try:
            self.world.send_chat(ctype, int(lang), text, target=target,
                                 channel=channel)
            echo_kind = "whisper" if kind == "whisper" else kind
            if kind in ("whisper", "channel", "say", "yell", "party",
                        "guild", "raid"):
                with self._lock:
                    self._seq += 1
                    label = f"-> {target or channel or echo_kind}"
                    self.history.append({
                        "id": self._seq, "ts": time.time(), "kind": "echo",
                        "ctype": ctype, "sender": label, "channel": channel,
                        "text": text, "lang": lang,
                    })
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def join(self, name: str, password: str = "") -> dict:
        if not self.world:
            return {"ok": False, "error": "not online"}
        try:
            self.world.join_channel(name, password)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def leave(self, name: str) -> dict:
        if not self.world:
            return {"ok": False, "error": "not online"}
        try:
            self.world.leave_channel(name)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def chan_list(self, name: str) -> dict:
        if not self.world:
            return {"ok": False, "error": "not online"}
        try:
            self.world.channel_list(name)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def who(self, **kw) -> dict:
        if not self.world:
            return {"ok": False, "error": "not online"}
        try:
            self.world.who(**kw)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_messages(self, since_id: int = 0, limit: int = 200) -> list[dict]:
        with self._lock:
            out = [m for m in self.history if m["id"] > since_id]
            return out[-limit:]

    def logout(self) -> dict:
        try:
            if self.world and self.state == "online":
                self._note("Logging out ...", "system")
                self.world.logout()
        finally:
            self.disconnect(silent=True)
            self.status = "logged out"
        return {"ok": True}

    def disconnect(self, silent: bool = False):
        self._stop.set()
        self._cleanup_nets()
        if not silent:
            self.status = "disconnected"
        self.state = "offline"
        self.character = ""

    def _cleanup_nets(self):
        try:
            if self.world:
                self.world.close()
        finally:
            self.world = None
        try:
            if self.auth:
                self.auth.close()
                self.auth.session_key = None
        finally:
            self.auth = None


def _fmt_who(d: dict) -> str:
    entries = d.get("entries", [])
    if not entries:
        return "(who: no matches)"
    lines = [f"who: {d.get('count', len(entries))} shown"]
    for e in entries[:50]:
        lines.append(f"  {e['name']} L{e['level']} zone={e['zone']} "
                     f"{('[' + e['guild'] + ']') if e['guild'] else ''}")
    return "\n".join(lines)


def _fmt_chan_list(d: dict) -> str:
    if d.get("error"):
        return f"(channel list error: {d['error']})"
    return (f"channel {d.get('channel')}: "
            f"{d.get('count', 0)} members")
