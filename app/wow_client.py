"""High-level WoW connection manager (thread-safe, UI-friendly).

Owns AuthClient + WorldClient, background pollers (ping every 30s,
event drain), message history buffer, connection state machine:

  offline -> auth -> world -> chars -> online -> offline

All blocking network errors surface as status dicts; passwords and
session keys are zeroed on disconnect.
"""
from __future__ import annotations

import concurrent.futures
import queue
import threading
import time

from wow.auth_socket import AuthClient
from wow.chat_defs import (
    SENDABLE,
    Language,
    default_language_for_race,
    faction_of_race,
    language_name,
)
from wow.world_socket import ChatLine, WorldClient

# Universal-first probe tuning. Scope: STOCK cores + Yggdrasil only.
# Stock ChatHandler always rejects client-sent LANG_UNIVERSAL for normal
# chat with SendNotification(LANG_UNKNOWN_LANGUAGE) -> SMSG_NOTIFICATION
# "Unknown language" (acore_string 805), so the match below is exact
# (case/whitespace-insensitive). Chat has no delivery ack, so silence
# within the window means "accepted".
PROBE_WINDOW = 4.0   # assume accepted if no rejection arrives within this
PROBE_GRACE = 10.0   # still honour late rejections for in-flight probes
STOCK_UNKNOWN_LANGUAGE_TEXT = "unknown language"
# AFK/DND are exempt from the Universal rejection on stock cores, so a
# probe with those types proves nothing -> always use the faction tongue.
NO_PROBE_KINDS = frozenset({"afk", "dnd"})


class WoWChatManager:
    def __init__(self, history_limit: int = 500):
        self._lock = threading.Lock()
        self.state = "offline"
        self.status = "idle"
        self.account = ""
        self.realm_name = ""
        self.character = ""
        self.faction = ""
        self.language = 7  # faction tongue; set on login from char race
        # Universal verdict cache (per session): None=unknown, True=accepted,
        # False=rejected (fall back to faction tongue without probing).
        self.universal_verdict: bool | None = None
        self._probes: list[dict] = []  # in-flight universal sends
        self._accept_noted = False
        self.auth: AuthClient | None = None
        self.world: WorldClient | None = None
        self.history: list[dict] = []
        self.history_limit = history_limit
        self._seq = 0
        self._ping_thread: threading.Thread | None = None
        self._drain_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.realms: list[dict] = []
        # Pending wizard state between phases (cleared on disconnect).
        self._session_key: bytes | None = None
        self._account_upper = ""
        self._realm_id = 0
        # Ring buffer of debug lines (also printed to stderr).
        self.debug_log: list[dict] = []
        # guid -> display name cache (filled via CMSG_NAME_QUERY).
        self.names: dict[int, str] = {}
        self._name_pending: set[int] = set()
        self.addon_dropped = 0

    def _dbg(self, msg: str):
        line = {"ts": time.time(), "msg": str(msg)}
        with self._lock:
            self.debug_log.append(line)
            if len(self.debug_log) > 300:
                del self.debug_log[: len(self.debug_log) - 300]
        print(f"[ygg] {line['msg']}", flush=True)

    def debug_tail(self, n: int = 40) -> list[dict]:
        with self._lock:
            return list(self.debug_log[-n:])

    @staticmethod
    def _run_guarded(fn, secs: float, label: str, close=None):
        """Run blocking network setup with a hard deadline so a stalled
        server can never hang the request forever. Abandoned worker
        threads die on their own socket timeouts."""
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(fn)
        try:
            return fut.result(timeout=secs)
        except concurrent.futures.TimeoutError:
            if close is not None:
                try:
                    close()
                except Exception:
                    pass
            raise TimeoutError(
                f"{label} timed out after {secs:.0f}s — server stalled "
                f"mid-handshake (firewall or overloaded server?)")
        finally:
            ex.shutdown(wait=False)

    # -- helpers ------------------------------------------------------
    def _push_line(self, line: ChatLine):
        # Blank system lines carry nothing — don't spam the feed.
        if not line.text.strip():
            return
        # Addon protocol (LANG_ADDON) is machine chatter the real client
        # routes to addons invisibly — never show it as chat.
        if line.lang == Language.ADDON:
            with self._lock:
                self.addon_dropped += 1
            return
        with self._lock:
            self._seq += 1
            self.history.append({
                "id": self._seq, "ts": line.ts, "kind": line.kind,
                "ctype": line.ctype, "sender": line.sender,
                "channel": line.channel, "text": line.text,
                "lang": line.lang, "sguid": line.sender_guid,
                "tguid": line.target_guid,
            })
            if len(self.history) > self.history_limit:
                del self.history[: len(self.history) - self.history_limit]
        # Player chat carries guids, not names — resolve in background so
        # the feed shows names instead of guid:12345.
        if line.sender_guid and not line.sender:
            self._maybe_query_name(line.sender_guid)

    def _note(self, text: str, kind: str = "system"):
        with self._lock:
            self._seq += 1
            self.history.append({
                "id": self._seq, "ts": time.time(), "kind": kind,
                "ctype": 0, "sender": "", "channel": "", "text": text,
                "lang": 0,
            })

    def _maybe_query_name(self, guid: int):
        with self._lock:
            if guid in self.names or guid in self._name_pending:
                return
            self._name_pending.add(guid)
        try:
            if self.world:
                self.world.name_query(guid)
        except Exception:
            pass

    def _on_name_query(self, detail: dict):
        guid = int(detail.get("guid", 0) or 0)
        name = str(detail.get("name", "") or "")
        if guid and name:
            with self._lock:
                self.names[guid] = name
                self._name_pending.discard(guid)
            self._dbg(f"world: guid {guid} is '{name}'")

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self.state, "status": self.status,
                "account": self.account, "realm": self.realm_name,
                "character": self.character, "faction": self.faction,
                "language": self.language,
                "universal": ("unknown" if self.universal_verdict is None
                              else "yes" if self.universal_verdict else "no"),
                "addon_dropped": self.addon_dropped,
            }

    # -- lifecycle: 1) auth -> realms  2) realm -> characters  3) enter --
    def fetch_realms(self, auth_host: str, auth_port: int, username: str,
                     password: str) -> dict:
        """Phase 1: SRP logon, return the realm list for user selection.

        The password is used for the handshake only and never stored;
        the session key is kept in memory for the world login (phase 2).
        """
        self.disconnect(silent=True)
        self._stop.clear()
        self.state = "auth"
        self.account = username
        self.status = f"authenticating {username}@{auth_host}:{auth_port} ..."
        self._dbg(f"auth: start for '{username}' @ {auth_host}:{auth_port}")
        auth = AuthClient(auth_host, int(auth_port), log=self._dbg)
        try:
            def _do():
                auth.logon(username, password)
                return auth.realm_list()
            realms = self._run_guarded(
                _do, 45.0, "auth login", close=auth.close)
            assert auth.session_key is not None
            self._session_key = bytes(auth.session_key)
            self._account_upper = username.upper()
            self.realms = [{"id": r.id, "name": r.name, "address": r.address,
                            "population": r.population} for r in realms]
            if not self.realms:
                raise ConnectionError("server returned no realms")
            self.state = "realms"
            self.status = f"authenticated — select a realm"
            self._dbg(f"auth: done, {len(self.realms)} realm(s)")
            return {"ok": True, "realms": self.realms}
        except Exception as exc:
            self.status = f"error: {exc}"
            self.state = "offline"
            self._dbg(f"auth: FAILED: {exc}")
            self._cleanup_nets()
            return {"ok": False, "error": str(exc)}
        finally:
            try:
                auth.close()
            except Exception:
                pass
            self.auth = None

    def fetch_characters(self, realm_id: int) -> dict:
        """Phase 2: world AUTH_SESSION + CHAR_ENUM for the chosen realm.

        Like a stock client, the world address comes straight from the
        realm list entry — no overrides.
        """
        if self.state != "realms" or self._session_key is None:
            return {"ok": False, "error": "authenticate first"}
        target = next((r for r in self.realms if r["id"] == int(realm_id)),
                      None)
        if target is None:
            return {"ok": False,
                    "error": f"unknown realm id {realm_id}"}
        host, _, port_s = target["address"].partition(":")
        port = int(port_s or 8085)
        self.realm_name = target["name"]
        self._realm_id = int(target["id"])
        self.status = f"world login {host}:{port} ..."
        self.state = "world"
        self._dbg(f"world: start login to {host}:{port} as "
                  f"{self._account_upper} (realm id {self._realm_id})")
        try:
            world = WorldClient()
            world.log = self._dbg
            def _do():
                world.connect(host, port)
                world.login(self._account_upper, self._session_key,
                            self._realm_id)
                return world
            self._run_guarded(_do, 60.0, "world login",
                              close=world.close)
            self.world = world
            chars = [{"guid": c.guid, "name": c.name, "level": c.level,
                      "race": c.race, "class": c.cls}
                     for c in world.characters]
            if not chars:
                raise ConnectionError("no characters on this realm/account")
            self.state = "chars"
            self.status = f"select a character on {target['name']}"
            self._dbg(f"world: ready, {len(chars)} character(s)")
            # Keepalive starts NOW, not on entering the world: the server
            # boots idle char-select connections, which used to look like
            # "Back button logged me out".
            self._start_ping_loop()
            self._start_drain_loop()
            return {"ok": True, "realm": self.realm_name, "characters": chars}
        except Exception as exc:
            self.status = f"error: {exc}"
            self.state = "realms"
            self._dbg(f"world: FAILED: {exc}")
            self._cleanup_world()
            return {"ok": False, "error": str(exc)}

    def enter_world(self, character_name: str = "") -> dict:
        """Phase 3: PLAYER_LOGIN for the chosen character, go online."""
        if self.state != "chars" or not self.world:
            return {"ok": False, "error": "select a realm first"}
        chars = [{"guid": c.guid, "name": c.name, "level": c.level,
                  "race": c.race, "class": c.cls}
                 for c in self.world.characters]
        pick = (character_name or "").strip() or (chars[0]["name"]
                                                  if chars else "")
        entry = next((c for c in chars if c["name"].lower() == pick.lower()),
                     None)
        if entry is None:
            return {"ok": False,
                    "error": f"character '{pick}' not found"}
        try:
            self.status = f"entering world as {entry['name']} ..."
            self.world.player_login(entry["guid"])
            self.character = entry["name"]
            self.faction = faction_of_race(entry.get("race", 0))
            self.language = default_language_for_race(entry.get("race", 0))
            self.state = "online"
            self.status = f"online as {self.character}"
            self._note(f"Logged in as {self.character} on {self.realm_name}. "
                       f"Say/Yell are proximity-based; join World channel with "
                       f"/join World if your server has one.")
            self._start_ping_loop()
            self._start_drain_loop()
            return {"ok": True, "character": self.character,
                    "realm": self.realm_name,
                    "faction": self.faction, "language": self.language}
        except Exception as exc:
            self.status = f"error: {exc}"
            self.state = "chars"
            return {"ok": False, "error": str(exc)}

    def _start_ping_loop(self):
        if self._ping_thread and self._ping_thread.is_alive():
            return
        self._ping_thread = threading.Thread(target=self._ping_loop,
                                             daemon=True)
        self._ping_thread.start()

    def _start_drain_loop(self):
        if self._drain_thread and self._drain_thread.is_alive():
            return
        self._drain_thread = threading.Thread(target=self._drain_loop,
                                              daemon=True)
        self._drain_thread.start()

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
                self._settle_probes()
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
                elif t == "name_query":
                    self._on_name_query(ev.get("detail", {}))
                elif t == "notification":
                    self._on_notification(str(ev.get("text", "")))
                elif t == "login_verify":
                    pass
                elif t == "parse_error":
                    pass
            except Exception:
                time.sleep(0.5)

    # -- actions ------------------------------------------------------
    def resolve_lang(self, lang, kind: str = "say") -> tuple[int, bool]:
        """Map a requested language to (tongue, probe?).

        lang: "auto"/None = Universal-first with fallback; a number forces
        that tongue with no fallback. While a probe is in flight, auto
        degrades to the safe faction tongue so one session costs at most
        one rejected send. AFK/DND never probe (stock accepts Universal
        for those regardless, so the result would be meaningless).
        """
        if lang is None or (isinstance(lang, str) and lang == "auto"):
            if kind in NO_PROBE_KINDS or self.universal_verdict is False:
                return self.language, False
            now = time.time()
            in_flight = any(now - p["ts"] < PROBE_WINDOW for p in self._probes)
            if self.universal_verdict is None and not in_flight:
                return 0, True
            if self.universal_verdict is True:
                return 0, False
            return self.language, False
        return int(lang), False

    def send(self, kind: str, text: str, target: str = "",
             channel: str = "", lang="auto") -> dict:
        if self.state != "online" or not self.world:
            return {"ok": False, "error": "not online"}
        tongue, probe = self.resolve_lang(lang, kind)
        ctype = int(SENDABLE.get(kind, SENDABLE["say"]))
        try:
            self.world.send_chat(ctype, tongue, text, target=target,
                                 channel=channel)
            if probe:
                self._probes.append({"ts": time.time(), "ctype": ctype,
                                     "text": text, "target": target,
                                     "channel": channel})
            echo_kind = "whisper" if kind == "whisper" else kind
            if kind in ("whisper", "channel", "say", "yell", "party",
                        "guild", "raid"):
                with self._lock:
                    self._seq += 1
                    label = (f"-> {target or channel or echo_kind} "
                             f"[{language_name(tongue)}]")
                    self.history.append({
                        "id": self._seq, "ts": time.time(), "kind": "echo",
                        "ctype": ctype, "sender": label, "channel": channel,
                        "text": text, "lang": tongue,
                    })
            return {"ok": True, "lang": tongue, "probed": probe}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _on_notification(self, text: str):
        """Rejection callback: stock "Unknown language" matching an
        in-flight Universal probe means the send never went out ->
        resend it in the faction tongue and cache the verdict."""
        if text.strip().lower() != STOCK_UNKNOWN_LANGUAGE_TEXT:
            return
        now = time.time()
        fresh = [p for p in self._probes if now - p["ts"] < PROBE_GRACE]
        if not fresh:
            return
        self._probes.clear()
        self.universal_verdict = False
        if not self.world:
            return
        for p in fresh:
            try:
                self.world.send_chat(p["ctype"], self.language, p["text"],
                                     target=p["target"], channel=p["channel"])
            except Exception:
                pass
        self._note(f"Universal rejected by server ({text.strip()}) — "
                   f"resent in {language_name(self.language)}.", "system")

    def _settle_probes(self):
        """No rejection within PROBE_WINDOW => server accepts Universal."""
        if self.universal_verdict is not None or not self._probes:
            return
        now = time.time()
        if all(now - p["ts"] >= PROBE_WINDOW for p in self._probes):
            self._probes.clear()
            self.universal_verdict = True
            if not self._accept_noted:
                self._accept_noted = True
                self._note("Server accepts Universal — using it.", "system")

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
            out = []
            for m in self.history:
                if m["id"] <= since_id:
                    continue
                m = dict(m)
                sguid = m.get("sguid") or 0
                if sguid and not m.get("sender"):
                    m["sender"] = self.names.get(
                        sguid, f"guid:{sguid}")
                out.append(m)
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
        for t in (self._ping_thread, self._drain_thread):
            if t and t.is_alive() and t is not threading.current_thread():
                t.join(timeout=2.0)
        self._ping_thread = None
        self._drain_thread = None
        if not silent:
            self.status = "disconnected"
        self.state = "offline"
        self.character = ""
        self.faction = ""
        self.language = 7
        self.universal_verdict = None
        self._probes = []
        self._accept_noted = False
        self.names = {}
        self._name_pending = set()
        self.addon_dropped = 0
        self.realms = []
        self.realm_name = ""
        self._realm_id = 0
        self._account_upper = ""
        if self._session_key:
            self._session_key = b"\x00" * len(self._session_key)
            self._session_key = None

    def _cleanup_world(self):
        """Drop the world connection but keep auth state (realm retry)."""
        try:
            if self.world:
                self.world.close()
        finally:
            self.world = None

    def _cleanup_nets(self):
        self._cleanup_world()
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
