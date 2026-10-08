"""Little packet reader/writer: C-strings, packed GUIDs, primitives."""
from __future__ import annotations

import struct


class Writer:
    def __init__(self):
        self.buf = bytearray()

    def u8(self, v: int) -> "Writer":
        self.buf += struct.pack("<B", v & 0xFF)
        return self

    def u16(self, v: int) -> "Writer":
        self.buf += struct.pack("<H", v & 0xFFFF)
        return self

    def u32(self, v: int) -> "Writer":
        self.buf += struct.pack("<I", v & 0xFFFFFFFF)
        return self

    def u64(self, v: int) -> "Writer":
        self.buf += struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF)
        return self

    def f32(self, v: float) -> "Writer":
        self.buf += struct.pack("<f", v)
        return self

    def cstr(self, s: str) -> "Writer":
        self.buf += s.encode("utf-8") + b"\x00"
        return self

    def raw(self, b: bytes) -> "Writer":
        self.buf += b
        return self

    def bytes(self) -> bytes:
        return bytes(self.buf)


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def left(self) -> int:
        return len(self.data) - self.pos

    def raw(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ValueError("packet underflow")
        out = self.data[self.pos: self.pos + n]
        self.pos += n
        return out

    def u8(self) -> int:
        return struct.unpack("<B", self.raw(1))[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.raw(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.raw(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.raw(8))[0]

    def f32(self) -> float:
        return struct.unpack("<f", self.raw(4))[0]

    def cstr(self) -> str:
        end = self.data.find(b"\x00", self.pos)
        if end < 0:
            raise ValueError("unterminated cstring")
        out = self.data[self.pos:end].decode("utf-8", "replace")
        self.pos = end + 1
        return out

    def packed_guid(self) -> int:
        """3.3.5a packed GUID: mask byte + present bytes -> uint64."""
        mask = self.u8()
        guid = 0
        for i in range(8):
            if mask & (1 << i):
                guid |= self.u8() << (i * 8)
        return guid

    def all_cstrings(self) -> list[str]:
        parts: list[str] = []
        pos = self.pos
        d = self.data
        while True:
            end = d.find(b"\x00", pos)
            if end < 0:
                break
            parts.append(d[pos:end].decode("utf-8", "replace"))
            pos = end + 1
        return parts


def pack_guid(guid: int) -> bytes:
    mask = 0
    body = bytearray()
    for i in range(8):
        b = (guid >> (i * 8)) & 0xFF
        if b:
            mask |= 1 << i
            body.append(b)
    return bytes([mask]) + bytes(body)
