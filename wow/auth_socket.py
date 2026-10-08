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
from . import net as netmod
from .opcodes import (
    BUILD,
    CMD_AUTH_LOGON_CHALLENGE,
    CMD_AUTH_LOGON_PROOF,
    CMD_REALM_LIST,
)

# AuthResult names from yggdrasilcore AuthCodes.h (subset seen on the wire).
AUTH_ERRORS = {
    0x00: "WOW_SUCCESS",
    0x03: "WOW_FAIL_BANNED (account or IP banned)",
    0x04: "WOW_FAIL_UNKNOWN_ACCOUNT",
    0x05: "WOW_FAIL_INCORRECT_PASSWORD",
    0x06: "WOW_FAIL_ALREADY_ONLINE",
    0x08: "WOW_FAIL_DB_BUSY",
    0x09: "WOW_FAIL_VERSION_INVALID (build rejected / StrictVersionCheck)",
    0x0C: "WOW_FAIL_SUSPENDED",
    0x10: "WOW_FAIL_LOCKED_ENFORCED (IP lock mismatch)",
    0x19: "WOW_FAIL_UNLOCKABLE_LOCK (country lock mismatch)",
}


def _auth_err(code: int) -> str:
    return AUTH_ERRORS.get(code, f"code={code:#04x}")


def build_logon_challenge(username: str, build: int = BUILD,
                          platform: str = "x86", os_: str = "Win",
                          locale: str = "enUS") -> bytes:
    """CMD_AUTH_LOGON_CHALLENGE packet. Must satisfy the server check
    (AuthSession::HandleLogonChallenge): size - 30 == I_len, else the
    server closes the connection without a reply."""
    uname = srp.upper_latin(username)
    body = (b"WoW\x00"
            + struct.pack("<BBB", 3, 3, 5) + struct.pack("<H", build)
            + platform.encode("ascii")[:4][::-1].ljust(4, b"\x00")
            + os_.encode("ascii")[:4][::-1].ljust(4, b"\x00")
            + locale.encode("ascii")[:4][::-1].ljust(4, b"\x00")
            + struct.pack("<I", 0)  # timezone bias
            + struct.pack("<I", 0)  # client ip
            + bytes([len(uname)])
            + uname.encode("ascii"))
    assert len(body) - 30 == len(uname), "challenge size invariant broken"
    return (bytes([CMD_AUTH_LOGON_CHALLENGE, 0])
            + struct.pack("<H", len(body)) + body)


@dataclass
class RealmEntry:
    id: int
    name: str
    address: str  # "host:port"
    population: float = 0.0


class AuthClient:
    def __init__(self, host: str, port: int = 3724, timeout: float = 8.0,
                 log=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._log = log or (lambda *a: None)
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
        self._log(f"auth: connecting to {self.host}:{self.port} ...")
        self.sock = netmod.connect_tcp(self.host, self.port, self.timeout,
                                       self._log)
        self.sock.settimeout(self.timeout)

    def _recv(self, n: int, what: str) -> bytes:
        assert self.sock
        self.sock.settimeout(self.timeout)
        out = bytearray()
        while len(out) < n:
            try:
                chunk = self.sock.recv(n - len(out))
            except (socket.timeout, TimeoutError):
                raise TimeoutError(
                    f"auth server stopped responding while: {what} "
                    f"(>{self.timeout:.0f}s, firewall or stalled server?)")
            if not chunk:
                raise ConnectionError(
                    f"auth server closed the connection while: {what}")
            out += chunk
        return bytes(out)

    def _byte(self, what: str) -> int:
        return self._recv(1, what)[0]

    # -- public --------------------------------------------------------
    def logon(self, username: str, password: str,
              platform: str = "x86", os_: str = "Win",
              locale: str = "enUS", build: int = BUILD) -> None:
        """Full SRP6 handshake. Sets self.session_key (40 bytes)."""
        self._connect()
        assert self.sock
        sock = self.sock
        uname = srp.upper_latin(username)
        pkt = build_logon_challenge(username, build, platform, os_, locale)
        sock.sendall(pkt)
        self._log(f"auth: logon challenge sent for '{uname}' "
                  f"({len(pkt)} bytes), awaiting reply ...")

        cmd = self._byte("logon-challenge reply")
        if cmd != CMD_AUTH_LOGON_CHALLENGE:
            raise ConnectionError(f"unexpected auth reply cmd=0x{cmd:02X}")
        # Server prefix is cmd, 0x00, status (LogonChallengeCallback sends
        # only these 3 bytes on failure, e.g. unknown account).
        _zero = self._byte("logon-challenge reply")
        status = self._byte("logon-challenge reply")
        if status != 0:
            raise PermissionError(
                f"auth rejected account '{uname}': {_auth_err(status)}"
                f"{' (no such account — check the exact account name)' if status == 0x04 else ''}")
        B_le = self._recv(32, "logon-challenge reply (B)")
        g_len = self._byte("logon-challenge reply (g)")
        _g = self._recv(g_len, "logon-challenge reply (g)")
        n_len = self._byte("logon-challenge reply (N)")
        N_le = self._recv(n_len, "logon-challenge reply (N)")
        salt = self._recv(32, "logon-challenge reply (salt)")
        _vc = self._recv(16, "logon-challenge reply (version challenge)")
        sec_flags = self._byte("logon-challenge reply (security flags)")
        self._log(f"auth: challenge ok (B/N/salt received, "
                  f"securityFlags={sec_flags})")
        if sec_flags not in (0, 1, 2, 4):
            raise PermissionError(
                f"account needs an unsupported second factor "
                f"(securityFlags={sec_flags})")
        if sec_flags & 0x01:
            # PIN input: u32 + 16-byte hash follows the flags byte.
            _pin = self._recv(4 + 16, "logon-challenge reply (PIN grid)")
            raise PermissionError("account requires PIN entry (unsupported)")
        if sec_flags & 0x02:
            # Matrix input: 4x u8 + u64.
            _mx = self._recv(4 + 8, "logon-challenge reply (matrix)")
            raise PermissionError(
                "account requires matrix-card entry (unsupported)")

        a, A_le = srp.generate_client_ephemeral()
        K, M1 = srp.compute_session_key(a, A_le, B_le, salt, username, password)
        crc = bytes(20)  # WoW.exe CRC; only checked with StrictVersionCheck
        sock.sendall(
            bytes([CMD_AUTH_LOGON_PROOF])
            + A_le
            + M1
            + crc
            + bytes([0, 0])  # keys=0, securityFlags=0
        )
        self._log("auth: logon proof sent, awaiting reply ...")

        cmd = self._byte("logon-proof reply")
        if cmd != CMD_AUTH_LOGON_PROOF:
            raise ConnectionError("expected auth proof reply, "
                                  f"got cmd=0x{cmd:02X}")
        err = self._byte("logon-proof reply")
        if err != 0:
            raise PermissionError(f"auth proof failed: {_auth_err(err)}")
        M2_server = self._recv(20, "logon-proof reply (M2)")
        # 3.x proof struct tail: AccountFlags u32 + SurveyId u32 +
        # LoginFlags u16 (AuthSession::sAuthLogonProof_S). Must consume all
        # of it or the realm-list reply desyncs.
        _tail = self._recv(10, "logon-proof reply (tail)")
        # verify server proof
        _, M2_expected = srp.client_proof(username, salt, A_le, B_le, K)
        # NOTE: client_proof recomputes M1 internally; compare M2 only.
        if M2_server != M2_expected:
            raise PermissionError("server proof mismatch (SRP math bug — "
                                  "please report with the debug log)")
        self.session_key = K
        self._log("auth: SRP verified, session key established")

    def realm_list(self) -> list[RealmEntry]:
        assert self.sock
        sock = self.sock
        # CMD_REALM_LIST request is 5 bytes (REALM_LIST_PACKET_SIZE).
        sock.sendall(bytes([CMD_REALM_LIST, 0, 0, 0, 0]))
        self._log("auth: realm list requested ...")
        cmd = self._byte("realm-list reply")
        if cmd != CMD_REALM_LIST:
            raise ConnectionError("expected realm list reply, "
                                  f"got cmd=0x{cmd:02X}")
        size = struct.unpack("<H", self._recv(2, "realm-list reply"))[0]
        blob = self._recv(size, f"realm-list body ({size} bytes)")
        import struct as _st

        pos = 4  # skip u32 zero
        if len(blob) < 6:
            raise ConnectionError("realm-list reply too short")
        n_realms = _st.unpack_from("<H", blob, pos)[0]
        pos += 2
        out = parse_realm_blob(blob[pos:], n_realms)
        self._log(f"auth: got {len(out)} realm(s): "
                  + ", ".join(f"{r.name} ({r.address})" for r in out))
        return out


def parse_realm_blob(blob: bytes, n_realms: int) -> list[RealmEntry]:
    """Parse realm entries (after the u32 zero + u16 count). Split out
    for testability. Handles REALM_FLAG_SPECIFYBUILD extra bytes."""
    import struct as _st

    pos = 0
    out: list[RealmEntry] = []
    for _ in range(n_realms):
        _type = blob[pos]
        pos += 1
        _locked = blob[pos]
        pos += 1
        flags = blob[pos]
        pos += 1
        end = blob.find(b"\x00", pos)
        if end < 0:
            raise ConnectionError("truncated realm-list entry (name)")
        name = blob[pos:end].decode("utf-8", "replace")
        pos = end + 1
        end = blob.find(b"\x00", pos)
        if end < 0:
            raise ConnectionError("truncated realm-list entry (address)")
        addr = blob[pos:end].decode("utf-8", "replace")
        pos = end + 1
        if len(blob) < pos + 7:
            raise ConnectionError("truncated realm-list entry (stats)")
        population = _st.unpack_from("<f", blob, pos)[0]
        pos += 4
        _n_chars = blob[pos]
        pos += 1
        _tz = blob[pos]
        pos += 1
        realm_id = blob[pos]
        pos += 1
        if flags & 0x04:  # REALM_FLAG_SPECIFYBUILD: 3xu8 + u16 follow
            pos += 5
        out.append(RealmEntry(id=realm_id, name=name, address=addr,
                              population=population))
    return out
