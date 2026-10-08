"""ARC4-drop1024 world packet crypt, compatible with AuthCrypt.

Server (AuthCrypt::Init):
  serverKey = HMAC-SHA1(key=ServerEncryptionKey, data=K)
  clientKey = HMAC-SHA1(key=ServerDecryptionKey, data=K)
  both ARC4 states drop first 1024 bytes.

This client mirrors it:
  - decrypts S->C headers with the *server* key stream,
  - encrypts C->S headers with the *client* key stream.

Only headers are encrypted (6-byte C->S, 4/5-byte S->C), exactly like
WorldSocket::Update / ReadHeaderHandler.
"""
from __future__ import annotations

import hashlib
import hmac

SERVER_ENCRYPTION_KEY = bytes(
    [0xCC, 0x98, 0xAE, 0x04, 0xE8, 0x97, 0xEA, 0xCA,
     0x12, 0xDD, 0xC0, 0x93, 0x42, 0x91, 0x53, 0x57]
)
SERVER_DECRYPTION_KEY = bytes(
    [0xC2, 0xB3, 0x72, 0x3C, 0xC6, 0xAE, 0xD9, 0xB5,
     0x34, 0x3C, 0x53, 0xEE, 0x2F, 0x43, 0x67, 0xCE]
)


class ARC4:
    def __init__(self, key: bytes):
        s = list(range(256))
        j = 0
        for i in range(256):
            j = (j + s[i] + key[i % len(key)]) & 0xFF
            s[i], s[j] = s[j], s[i]
        self.s = s
        self.i = 0
        self.j = 0

    def crypt(self, data: bytes) -> bytes:
        s, i, j = self.s, self.i, self.j
        out = bytearray(len(data))
        for n, b in enumerate(data):
            i = (i + 1) & 0xFF
            j = (j + s[i]) & 0xFF
            s[i], s[j] = s[j], s[i]
            out[n] = b ^ s[(s[i] + s[j]) & 0xFF]
        self.i, self.j = i, j
        return bytes(out)


class WorldCrypt:
    """Client-side world crypt. Call init(K) after AUTH_SESSION digest."""

    def __init__(self):
        self._enc: ARC4 | None = None  # C->S
        self._dec: ARC4 | None = None  # S->C

    @property
    def initialized(self) -> bool:
        return self._enc is not None

    def init(self, K: bytes):
        enc_key = hmac.new(SERVER_DECRYPTION_KEY, K, hashlib.sha1).digest()
        dec_key = hmac.new(SERVER_ENCRYPTION_KEY, K, hashlib.sha1).digest()
        self._enc = ARC4(enc_key)
        self._dec = ARC4(dec_key)
        drop = bytes(1024)
        self._enc.crypt(drop)
        self._dec.crypt(drop)

    def encrypt_send(self, header: bytes) -> bytes:
        assert self._enc
        return self._enc.crypt(header)

    def decrypt_recv(self, header: bytes) -> bytes:
        assert self._dec
        return self._dec.crypt(header)
