"""Worldserver client (chat-only): AUTH_SESSION -> CHAR_ENUM -> PLAYER_LOGIN.

Covers, per yggdrasilcore sources:
- SMSG_AUTH_CHALLENGE: uint32(1) + authSeed(4) + rand(32)  [WorldSocket.cpp]
- CMSG_AUTH_SESSION field order [WorldSocket::HandleAuthSession]:
    build u32, loginServerID u32, account cstr, loginServerType u32,
    clientSeed u32, regionID u32, battlegroupID u32, realmID u32,
    dosResponse u64, digest(20), addonInfo(blob)
  digest = SHA1(UPPER(account), 0,0,0,0, clientSeedLE, serverSeed, K)
- AddonInfo: u32 blobLen + zlib(compressed(u32 count=0 + u32 time=0))
- Headers: C->S u16 BE size(=payload+4) + u32 LE opcode, ARC4'd after auth.
  S->C u16 BE size(=payload+2) + u16 LE opcode (3-byte large variant
  supported), ARC4'd after auth.
- Chat send layouts [ChatHandler::HandleMessagechatOpcode]:
    SAY/YELL/EMOTE/PARTY/GUILD/...: u32 type, u32 lang, cstr msg
    WHISPER: u32 type, u32 lang, cstr to, cstr msg
    CHANNEL: u32 type, u32 lang, cstr channel, cstr msg
- Channel ops [ChannelHandler.cpp]:
    JOIN: u32 chanId(0), u8 0, u8 0, cstr name, cstr pass
    LEAVE: u32 0, cstr name
    LIST: cstr name
"""
from __future__ import annotations

import hashlib
import queue
import socket
import struct
import threading
import time
import zlib
from dataclasses import dataclass, field

from .chat_defs import CHAT_TYPE_NAMES, ChannelNotify
from .crypt import WorldCrypt
from . import net as netmod
from .opcodes import Opcode
from .protocol import Reader, Writer


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    out = bytearray()
    while len(out) < n:
        chunk = sock.recv(n - len(out))
        if not chunk:
            raise ConnectionError("world connection closed")
        out += chunk
    return bytes(out)


@dataclass
class ChatLine:
    ts: float
    opcode: int
    ctype: int
    kind: str
    sender: str
    channel: str
    text: str
    lang: int = 0
    raw: str = ""


@dataclass
class CharacterInfo:
    guid: int
    name: str
    level: int = 0
    race: int = 0
    cls: int = 0
    zone: int = 0
    map: int = 0


def build_auth_session(account: str, client_seed: int, server_seed: bytes,
                       K: bytes, realm_id: int, build: int = 12340) -> bytes:
    upper = account.upper().encode("utf-8")
    digest = hashlib.sha1(
        upper + b"\x00\x00\x00\x00"
        + struct.pack("<I", client_seed) + bytes(server_seed) + K
    ).digest()
    addon_plain = struct.pack("<II", 0, 0)
    addon_blob = zlib.compress(addon_plain)
    w = Writer()
    w.u32(build).u32(0).cstr(account.upper()).u32(0)
    w.raw(struct.pack("<I", client_seed))
    w.u32(0).u32(0).u32(realm_id).u64(0)
    w.raw(digest)
    w.u32(len(addon_blob)).raw(addon_blob)
    return w.bytes()


def build_client_header(opcode: int, payload_len: int) -> bytes:
    size = payload_len + 4
    return struct.pack(">H", size) + struct.pack("<I", opcode)


class WorldClient:
    """Blocking world connection with a background reader thread."""

    def __init__(self):
        self.sock: socket.socket | None = None
        self.crypt = WorldCrypt()
        self.K: bytes | None = None
        self.inbox: "queue.Queue[ChatLine]" = queue.Queue()
        self.events: "queue.Queue[dict]" = queue.Queue()
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None
        self._ping_seq = 0
        self.player_guid: int = 0
        self.characters: list[CharacterInfo] = []
        self.pending_auth_response: "queue.Queue[dict]" = queue.Queue()
        self.server_seed: bytes = b"\x00\x00\x00\x00"
        self.auth_ok = False
        self._lock = threading.Lock()
        self.log = None  # set by manager: log(str) -> None

    def _log(self, msg: str):
        try:
            if self.log:
                self.log(msg)
        except Exception:
            pass

    # -- connect / login --------------------------------------------
    def connect(self, host: str, port: int, timeout: float = 8.0):
        self.close()
        self._stop.clear()
        self._log(f"world: connecting to {host}:{port} ...")
        self.sock = netmod.connect_tcp(host, port, timeout,
                                       lambda m: self._log(m))
        self.sock.settimeout(90.0)
        self._read_challenge()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_challenge(self):
        assert self.sock
        opcode, payload = self._recv_packet_raw()
        if opcode != int(Opcode.SMSG_AUTH_CHALLENGE):
            raise ConnectionError(f"expected AUTH_CHALLENGE, got 0x{opcode:04X}")
        r = Reader(payload)
        r.u32()  # unk (1)
        self.server_seed = r.raw(4)
        # remaining 32 random bytes ignored
        self._log("world: auth challenge received, sending AUTH_SESSION ...")

    def login(self, account: str, K: bytes, realm_id: int,
              client_seed: int | None = None,
              wait_auth: float = 15.0, wait_chars: float = 15.0):
        import secrets as _secrets
        assert self.sock
        self.K = bytes(K)
        seed = client_seed if client_seed is not None else \
            int.from_bytes(_secrets.token_bytes(4), "little")
        payload = build_auth_session(account, seed, self.server_seed, self.K,
                                     realm_id)
        self.crypt.init(self.K)
        self._send(int(Opcode.CMSG_AUTH_SESSION), payload)
        t0 = time.time()
        while time.time() - t0 < wait_auth:
            try:
                msg = self.pending_auth_response.get(timeout=0.2)
            except queue.Empty:
                continue
            if not msg.get("ok"):
                raise PermissionError(f"world auth failed: {msg.get('detail')}")
            self.auth_ok = True
            break
        if not self.auth_ok:
            raise TimeoutError("no SMSG_AUTH_RESPONSE "
                               f"(>{wait_auth:.0f}s, wrong session key?)")
        self._log("world: AUTH_SESSION accepted")
        self.request_char_enum()
        t0 = time.time()
        while time.time() - t0 < wait_chars:
            if self.characters:
                self._log("world: got "
                          f"{len(self.characters)} character(s): "
                          + ", ".join(c.name for c in self.characters))
                return
            time.sleep(0.1)
        raise TimeoutError("no SMSG_CHAR_ENUM (empty account or wrong realm?)")

    # -- low-level send/recv -----------------------------------------
    def _send(self, opcode: int, payload: bytes):
        assert self.sock
        hdr = build_client_header(opcode, len(payload))
        if self.crypt.initialized:
            hdr = self.crypt.encrypt_send(hdr)
        with self._lock:
            assert self.sock
            self.sock.sendall(hdr + payload)

    def _recv_packet_raw(self) -> tuple[int, bytes]:
        assert self.sock
        hdr = _recv_exact(self.sock, 4)
        if self.crypt.initialized:
            hdr = self.crypt.decrypt_recv(hdr)
        size = struct.unpack(">H", hdr[:2])[0]
        opcode = struct.unpack("<H", hdr[2:4])[0]
        if size & 0x8000:  # large packet: one more size byte (server-side)
            extra = _recv_exact(self.sock, 1)
            if self.crypt.initialized:
                # NOTE: large headers (>32k payloads) are only used for
                # compressed update objects which a chat client ignores;
                # still consume correctly.
                extra = self.crypt.decrypt_recv(extra)
            size = ((size & 0x7FFF) << 8) | extra[0]
        payload = _recv_exact(self.sock, size - 2) if size >= 2 else b""
        return opcode, payload

    # -- reader thread ------------------------------------------------
    def _read_loop(self):
        try:
            while not self._stop.is_set():
                try:
                    opcode, payload = self._recv_packet_raw()
                except (ConnectionError, OSError, ValueError):
                    self.events.put({"t": "disconnect"})
                    return
                try:
                    self._dispatch(opcode, payload)
                except Exception as exc:  # never kill reader on parse errors
                    self.events.put({"t": "parse_error",
                                     "opcode": opcode, "detail": str(exc)})
        finally:
            pass

    def _dispatch(self, opcode: int, payload: bytes):
        if opcode == int(Opcode.SMSG_AUTH_RESPONSE):
            code = payload[0] if payload else 0xFF
            # AUTH_OK == 0x0C in 3.3.5a; anything else is an error.
            if code == 0x0C:
                self.pending_auth_response.put({"ok": True})
                # queue time info follows; ignored
            else:
                self.pending_auth_response.put(
                    {"ok": False, "detail": f"code=0x{code:02X}"})
            return
        if opcode == int(Opcode.SMSG_CHAR_ENUM):
            self.characters = parse_char_enum(payload)
            self.events.put({"t": "char_enum",
                             "chars": [c.name for c in self.characters]})
            return
        if opcode in (int(Opcode.SMSG_MESSAGECHAT),
                      int(Opcode.SMSG_GM_MESSAGECHAT)):
            line = parse_chat_packet(opcode, payload)
            if line:
                self.inbox.put(line)
            return
        if opcode == int(Opcode.SMSG_CHANNEL_NOTIFY):
            self.events.put({"t": "channel_notify",
                             "detail": parse_channel_notify(payload)})
            # also surface as a chat line for visibility
            d = parse_channel_notify(payload)
            self.inbox.put(ChatLine(ts=time.time(), opcode=opcode, ctype=-1,
                                    kind="notice",
                                    sender=d.get("channel", ""),
                                    channel=d.get("channel", ""),
                                    text=d.get("text", ""),
                                    raw=str(d)))
            return
        if opcode == int(Opcode.SMSG_CHANNEL_LIST):
            self.events.put({"t": "channel_list",
                             "detail": parse_channel_list(payload)})
            return
        if opcode == int(Opcode.SMSG_NOTIFICATION):
            text = parse_notification(payload)
            self.events.put({"t": "notification", "text": text})
            self.inbox.put(ChatLine(ts=time.time(), opcode=opcode, ctype=-1,
                                    kind="system", sender="", channel="",
                                    text=text))
            return
        if opcode == int(Opcode.SMSG_WHO):
            self.events.put({"t": "who", "detail": parse_who(payload)})
            return
        if opcode == int(Opcode.SMSG_NAME_QUERY_RESPONSE):
            self.events.put({"t": "name_query",
                             "detail": parse_name_query(payload)})
            return
        if opcode == int(Opcode.SMSG_PONG):
            self.events.put({"t": "pong"})
            return
        if opcode == int(Opcode.SMSG_LOGIN_VERIFY_WORLD):
            r = Reader(payload)
            m, x, y, z, o = r.u32(), r.f32(), r.f32(), r.f32(), r.f32()
            self.events.put({"t": "login_verify",
                             "detail": {"map": m, "x": x, "y": y, "z": z}})
            return
        if opcode == int(Opcode.SMSG_LOGOUT_RESPONSE):
            self.events.put({"t": "logout_response",
                             "detail": {"code": payload[0] if payload else -1}})
            return
        if opcode == int(Opcode.SMSG_LOGOUT_COMPLETE):
            self.events.put({"t": "logout_complete"})
            return
        if opcode == int(Opcode.SMSG_COMPRESSED_UPDATE_OBJECT):
            return  # chat client ignores movement/object data
        # everything else: stash minimal info for debugging
        self.events.put({"t": "opcode", "opcode": opcode, "len": len(payload)})

    # -- logged-in actions --------------------------------------------
    def request_char_enum(self):
        self.characters = []
        self._send(int(Opcode.CMSG_CHAR_ENUM), b"")

    def player_login(self, guid: int, wait_verify: float = 20.0) -> dict:
        self.player_guid = guid
        self._send(int(Opcode.CMSG_PLAYER_LOGIN),
                   struct.pack("<Q", guid))
        t0 = time.time()
        while time.time() - t0 < wait_verify:
            try:
                ev = self.events.get(timeout=0.3)
            except queue.Empty:
                continue
            if ev.get("t") == "login_verify":
                # re-queue for consumers then return
                self.events.put(ev)
                return ev["detail"]
            self.events.put(ev)
            time.sleep(0.05)
        raise TimeoutError("no SMSG_LOGIN_VERIFY_WORLD")

    def ping(self):
        self._ping_seq += 1
        self._send(int(Opcode.CMSG_PING),
                   struct.pack("<II", self._ping_seq, 0))

    def keep_alive(self):
        self._send(int(Opcode.CMSG_KEEP_ALIVE), b"")

    def send_chat(self, ctype: int, lang: int, text: str,
                  target: str = "", channel: str = ""):
        text = text[:255]
        w = Writer()
        w.u32(ctype & 0xFFFFFFFF).u32(lang & 0xFFFFFFFF)
        if ctype == 0x07:  # whisper
            w.cstr(target).cstr(text)
        elif ctype == 0x11:  # channel
            w.cstr(channel).cstr(text)
        else:
            w.cstr(text)
        self._send(int(Opcode.CMSG_MESSAGECHAT), w.bytes())

    def join_channel(self, name: str, password: str = ""):
        w = Writer()
        w.u32(0).u8(0).u8(0).cstr(name).cstr(password)
        self._send(int(Opcode.CMSG_JOIN_CHANNEL), w.bytes())

    def leave_channel(self, name: str):
        w = Writer()
        w.u32(0).cstr(name)
        self._send(int(Opcode.CMSG_LEAVE_CHANNEL), w.bytes())

    def channel_list(self, name: str):
        self._send(int(Opcode.CMSG_CHANNEL_LIST), Writer().cstr(name).bytes())

    def who(self, name_sub: str = "", zone_sub: str = "", min_level: int = 1,
            max_level: int = 80, race_mask: int = 0xFFFF,
            class_mask: int = 0xFFFF, stranger_only: bool = False):
        w = Writer()
        w.u32(min_level).u32(max_level).cstr(name_sub).cstr("")  # guild
        w.u32(race_mask).u32(class_mask)
        w.u32(0xFFFFFFFF).u32(0)  # zone ids: wildcard-ish
        w.cstr(zone_sub)
        w.cstr("")  # strings[0]
        w.u8(0 if not stranger_only else 1)
        self._send(int(Opcode.CMSG_WHO), w.bytes())

    def name_query(self, guid: int):
        self._send(int(Opcode.CMSG_NAME_QUERY), struct.pack("<Q", guid))

    def logout(self, wait: float = 5.0):
        try:
            self._send(int(Opcode.CMSG_LOGOUT_REQUEST), b"")
        except (OSError, AssertionError, ValueError):
            pass
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                ev = self.events.get(timeout=0.3)
            except queue.Empty:
                continue
            if ev.get("t") in ("logout_complete", "logout_response",
                               "disconnect"):
                self.events.put(ev)
                break
            self.events.put(ev)

    def close(self):
        self._stop.set()
        try:
            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.sock.close()
        finally:
            self.sock = None
        self.auth_ok = False
        if self.K:
            self.K = b"\x00" * len(self.K)
            self.K = None


# -- parsers -----------------------------------------------------------

def parse_char_enum(payload: bytes) -> list[CharacterInfo]:
    r = Reader(payload)
    if r.left() < 1:
        return []
    count = r.u8()
    out: list[CharacterInfo] = []
    for _ in range(count):
        try:
            guid = r.u64()
            name = r.cstr()
            race = r.u8()
            cls = r.u8()
            _gender = r.u8()
            _skin = r.u8()
            _face = r.u8()
            _hair = r.u8()
            _haircolor = r.u8()
            _facial = r.u8()
            level = r.u8()
            zone = r.u32()
            mmap = r.u32()
            x, y, z = r.f32(), r.f32(), r.f32()
            _guild = r.u32()
            _flags = r.u32()
            _firstlogin = r.u8()
            _petdisplay = r.u32()
            _petlevel = r.u32()
            _petfam = r.u32()
            # equipment: 23 x (displayid u32, invtype u8) in 3.3.5
            for _i in range(23):
                r.u32()
                r.u8()
            out.append(CharacterInfo(guid=guid, name=name, level=level,
                                     race=race, cls=cls, zone=zone, map=mmap))
        except ValueError:
            break
    return out


def _read_guid_and_rest(payload: bytes):
    """Shared tolerant SMSG_MESSAGECHAT body parser.

    Real layout (Chat.cpp BuildChatPacket, non-GM player chat):
      u8 type, u32 lang, packed senderGUID, u32 flags,
      [channel cstr if type==CHANNEL], packed targetGUID,
      u32 msgLen, msgBytes, u8 chatTag
    GM variant inserts u32+name before channel/target parts.
    """
    r = Reader(payload)
    ctype = r.u8()
    lang = r.u32()
    sender_guid = r.packed_guid()
    flags = r.u32()
    channel = ""
    sender_name = ""
    # Peek: try GM-style sender name prefix (u32 len + bytes + '\0').
    # Only treat as name if it parses cleanly AND enough bytes remain.
    save = r.pos
    gm_name = ""
    try:
        if r.left() >= 5:
            nlen = r.u32()
            if 1 < nlen <= 64 and r.left() >= nlen:
                cand = r.raw(nlen)
                if cand.endswith(b"\x00"):
                    gm_name = cand[:-1].decode("utf-8", "replace")
                    if not gm_name.replace("_", "").replace("-", "").isalnum() \
                            and len(gm_name) > 12:
                        raise ValueError("not a name")
                else:
                    raise ValueError("not a name")
            else:
                raise ValueError("not a name")
        else:
            raise ValueError("not a name")
    except (ValueError, UnicodeDecodeError):
        r.pos = save
        gm_name = ""
    if ctype == 0x11:  # channel
        try:
            channel = r.cstr()
        except ValueError:
            r.pos = save
    target_guid = 0
    try:
        if r.left() >= 1:
            target_guid = r.packed_guid()
    except ValueError:
        pass
    # message: u32 len + bytes (may include trailing \0), then u8 tag
    text = ""
    try:
        if r.left() >= 4:
            mlen = r.u32()
            if 0 < mlen <= r.left() + 1 and mlen <= 1024:
                raw = r.raw(min(mlen, r.left()))
                text = raw.split(b"\x00")[0].decode("utf-8", "replace")
            else:
                raise ValueError("bad msglen")
        else:
            raise ValueError("no msg")
    except ValueError:
        # fallback: last cstring in packet is the message
        strs = Reader(payload).all_cstrings()
        text = strs[-1] if strs else ""
    return {
        "type": ctype, "lang": lang, "sender_guid": sender_guid,
        "target_guid": target_guid, "channel": channel,
        "sender_name": sender_name or gm_name, "text": text,
    }


def parse_chat_packet(opcode: int, payload: bytes) -> ChatLine | None:
    if len(payload) < 6:
        return None
    try:
        d = _read_guid_and_rest(payload)
    except Exception:
        return None
    ctype = d["type"]
    kind = CHAT_TYPE_NAMES.get(ctype, f"msg_0x{ctype:02X}")
    if ctype == 0x11:
        kind = "channel"
    elif ctype in (0x07, 0x08, 0x09):
        kind = "whisper"
    # sender display: prefer embedded name, else guid
    sender = d["sender_name"] or f"guid:{d['sender_guid']}"
    # Try to recover an extra display name from trailing cstrings for
    # non-GM packets: [ ..., senderName?, message ]. Heuristic: if the
    # packet has >=2 cstrings and type needs a name, use second-to-last.
    try:
        strs = Reader(payload).all_cstrings()
        if len(strs) >= 2 and not d["sender_name"]:
            # channel packets: [channel, message]; plain: [message]
            pass
    except Exception:
        pass
    return ChatLine(ts=time.time(), opcode=opcode, ctype=ctype, kind=kind,
                    sender=sender, channel=d["channel"], text=d["text"],
                    lang=d["lang"])


def parse_channel_notify(payload: bytes) -> dict:
    try:
        r = Reader(payload)
        ntype = r.u8()
        try:
            tname = ChannelNotify(ntype).name
        except ValueError:
            tname = f"0x{ntype:02X}"
        channel = ""
        try:
            channel = r.cstr()
        except ValueError:
            pass
        rest = Reader(payload).all_cstrings()
        names = rest[1:] if rest else []
        text = f"[{tname}] " + " ".join(names)
        return {"notify": tname, "channel": channel, "names": names,
                "text": text.strip()}
    except Exception as exc:
        return {"notify": "UNKNOWN", "channel": "", "names": [],
                "text": f"(unparsed notify: {exc})"}


def parse_notification(payload: bytes) -> str:
    # ChatHandler::SendNotification: one null-terminated string per packet.
    try:
        return Reader(payload).cstr()
    except ValueError:
        return bytes(payload).split(b"\x00")[0].decode("utf-8", "replace")


def parse_channel_list(payload: bytes) -> dict:
    try:
        r = Reader(payload)
        channel = r.cstr()
        _flags = r.u8()
        count = r.u32()
        members: list[dict] = []
        for _ in range(min(count, 500)):
            guid = r.packed_guid()
            _virt = r.u8()
            members.append({"guid": guid})
        return {"channel": channel, "count": count, "members": members}
    except Exception as exc:
        return {"channel": "", "count": 0, "members": [],
                "error": str(exc)}


def parse_who(payload: bytes) -> dict:
    try:
        r = Reader(payload)
        displayed = r.u32()
        _total = r.u32()
        entries = []
        for _ in range(min(displayed, 100)):
            name = r.cstr()
            guild = r.cstr()
            level = r.u32()
            cls = r.u32()
            race = r.u32()
            _unk = r.u8()
            zone = r.u32()
            entries.append({"name": name, "guild": guild, "level": level,
                            "class": cls, "race": race, "zone": zone})
        # trailing cstring block ignored
        return {"count": displayed, "entries": entries}
    except Exception as exc:
        return {"count": 0, "entries": [], "error": str(exc)}


def parse_name_query(payload: bytes) -> dict:
    try:
        r = Reader(payload)
        guid = r.packed_guid()
        name = r.cstr() if r.left() else ""
        return {"guid": guid, "name": name}
    except Exception as exc:
        return {"guid": 0, "name": "", "error": str(exc)}
