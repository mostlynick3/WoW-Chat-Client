"""Authserver (3724) client: SRP6 logon + realm list.

Packet layouts from wowdev wiki (3.3.5a) with tolerant parsing:
  C->S CMD_AUTH_LOGON_CHALLENGE (0x00)
  S->C ... B(32) g N s(32) ...
  C->S CMD_AUTH_LOGON_PROOF (0x01): A(32) M1(20) crc(20) keys(1) sec(1)
  S->C ... M2(20) ...
  C->S CMD_REALM_LIST (0x10); S->C realm list (name, addr, realm id...).
"""
from __future__ import annotations

import hashlib
import socket
import struct
from dataclasses import dataclass

from . import srp
from .opcodes import (
    BUILD,
    CMD_AUTH_LOGON_CHALLENGE,
    CMD_AUTH_LOGON_PROOF,
    CMD_REALM_LIST,
)


@dataclass
class RealmEntry:
    id: int
    name: str
    address: str  # "host:port"
    population: float = 0.0


def _recv_all(sock: socket.socket, n: int, timeout: float = 15.0) -> bytes:
    sock.settimeout(timeout)
    out = bytearray()
    while len(out) < n:
        chunk = sock.recv(n - len(out))
        if not chunk:
            raise ConnectionError("auth connection closed")
        out += chunk
    return bytes(out)


def _read_byte(sock: socket.socket) -> int:
    return _recv_all(sock, 1)[0]


class AuthClient:
    def __init__(self, host: str, port: int = 3724, timeout: float = 15.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.session_key: bytes | None = None  # 40-byte K

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        finally:
            self.sock = None

    # -- low level -----------------------------------------------------
    def _connect(self):
        self.close()
        self.sock = socket.create_connection((self.host, self.port), self.timeout)

    # -- public --------------------------------------------------------
    def logon(self, username: str, password: str,
              platform: str = "x86", os_: str = "Win",
              locale: str = "enUS", build: int = BUILD) -> None:
        """Full SRP6 handshake. Sets self.session_key (40 bytes)."""
        self._connect()
        assert self.sock
        sock = self.sock
        uname = srp.upper_latin(username)

        game = b"WoW\x00"
        ver = struct.pack("<BBB", 3, 3, 5) + struct.pack("<H", build)
        plat = platform.encode("ascii")[:4][::-1].ljust(4, b"\x00")
        osb = os_.encode("ascii")[:4][::-1].ljust(4, b"\x00")
        # locale sent reversed on wire in most docs ("suNE" for enUS)
        loc = locale.encode("ascii")[:4][::-1].ljust(4, b"\x00")
        pkt = (
            bytes([CMD_AUTH_LOGON_CHALLENGE, 0])
            + struct.pack("<H", 4 + 4 + 4 + 4 + 4 + 4 + 4 + len(uname) + 4 + 2 + 1 + len(uname))
            + game
            + ver
            + plat
            + osb
            + loc
            + struct.pack("<I", 0)  # timezone bias
            + struct.pack("<I", 0)  # client ip
            + bytes([len(uname)])
            + uname.encode("ascii")
        )
        # size field = remaining bytes after initial 3 (cmd+err+size)
        # recompute defensively:
        body = pkt[3:]
        pkt = pkt[:1] + pkt[1:2] + struct.pack("<H", len(body)) + body
        sock.sendall(pkt)

        cmd = _read_byte(sock)
        if cmd != CMD_AUTH_LOGON_CHALLENGE:
            raise ConnectionError(f"unexpected auth reply cmd=0x{cmd:02X}")
        err = _read_byte(sock)
        if err != 0:
            raise PermissionError(f"auth logon challenge failed, code={err}")
        _recv_all(sock, 1)  # unk
        B_le = _recv_all(sock, 32)
        g_len = _read_byte(sock)
        _recv_all(sock, g_len)  # g (7)
        n_len = _read_byte(sock)
        N_le = _recv_all(sock, n_len)
        salt = _recv_all(sock, 32)
        _recv_all(sock, 16)  # unk3
        sec_flags = _read_byte(sock)
        if sec_flags not in (0, 1, 2, 4):
            pass  # authenticator/pin flows not supported in v1 chat client

        a, A_le = srp.generate_client_ephemeral()
        K, M1 = srp.compute_session_key(a, A_le, B_le, salt, username, password)
        crc = bytes(20)  # WoW.exe CRC; private servers usually ignore
        sock.sendall(
            bytes([CMD_AUTH_LOGON_PROOF])
            + A_le
            + M1
            + crc
            + bytes([0, 0])  # keys=0, securityFlags=0
        )

        cmd = _read_byte(sock)
        if cmd != CMD_AUTH_LOGON_PROOF:
            raise ConnectionError("expected auth proof reply")
        err = _read_byte(sock)
        if err != 0:
            raise PermissionError(f"auth proof failed, code={err} (bad password?)")
        M2_server = _recv_all(sock, 20)
        _recv_all(sock, 4)  # accountFlags + surveyId + unkFlags (tolerant: 4)
        # verify server proof
        _, M2_expected = srp.client_proof(username, salt, A_le, B_le, K)
        # NOTE: client_proof recomputes M1 internally; compare M2 only.
        if M2_server != M2_expected:
            raise PermissionError("server proof mismatch (wrong password or SRP bug)")
        self.session_key = K

    def realm_list(self) -> list[RealmEntry]:
        assert self.sock
        sock = self.sock
        # CMD_REALM_LIST header: cmd + 3 zero padding bytes (standard client)
        sock.sendall(bytes([CMD_REALM_LIST, 0, 0, 0, 0]))
        cmd = _read_byte(sock)
        if cmd != CMD_REALM_LIST:
            raise ConnectionError("expected realm list reply")
        size = struct.unpack("<H", _recv_all(sock, 2))[0]
        blob = _recv_all(sock, size)
        import struct as _st

        pos = 4  # skip unknown uint32
        n_realms = _st.unpack_from("<H", blob, pos)[0]
        pos += 2
        out: list[RealmEntry] = []
        for _ in range(n_realms):
            _type = blob[pos]
            pos += 1
            locked = blob[pos]
            pos += 1
            flags = blob[pos]
            pos += 1
            end = blob.find(b"\x00", pos)
            name = blob[pos:end].decode("utf-8", "replace")
            pos = end + 1
            end = blob.find(b"\x00", pos)
            addr = blob[pos:end].decode("utf-8", "replace")
            pos = end + 1
            population = _st.unpack_from("<f", blob, pos)[0]
            pos += 4
            n_chars = blob[pos]
            pos += 1
            tz = blob[pos]
            pos += 1
            realm_id = blob[pos]
            pos += 1
            out.append(RealmEntry(id=realm_id, name=name, address=addr,
                                  population=population))
        return out
