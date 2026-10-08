"""Offline unit tests (no server needed). Run: python3 -m unittest discover -s tests"""
import struct
import sys
import os
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wow import crypt as crypt_mod
from wow import protocol as P
from wow import srp
from wow.chat_defs import (
    Language,
    default_language_for_race,
    faction_of_race,
)
from wow.opcodes import Opcode
from wow.world_socket import (
    build_auth_session,
    build_client_header,
    parse_channel_list,
    parse_chat_packet,
    parse_who,
)


class TestOpcodes(unittest.TestCase):
    def test_pinned_values(self):
        self.assertEqual(int(Opcode.CMSG_MESSAGECHAT), 0x095)
        self.assertEqual(int(Opcode.SMSG_MESSAGECHAT), 0x096)
        self.assertEqual(int(Opcode.CMSG_JOIN_CHANNEL), 0x097)
        self.assertEqual(int(Opcode.CMSG_AUTH_SESSION), 0x1ED)
        self.assertEqual(int(Opcode.SMSG_AUTH_CHALLENGE), 0x1EC)


class TestCrypt(unittest.TestCase):
    def test_roundtrip_and_drop(self):
        # ARC4 is symmetric: fresh instances with the same key invert.
        import hashlib
        import hmac as hmac_mod
        K = bytes(range(40))
        key = hmac_mod.new(crypt_mod.SERVER_DECRYPTION_KEY, K,
                           hashlib.sha1).digest()
        a, b = crypt_mod.ARC4(key), crypt_mod.ARC4(key)
        for arc in (a, b):
            arc.crypt(bytes(1024))  # drop1024 like AuthCrypt
        hdr = b"\x00\x06\xed\x01\x00\x00"
        enc = a.crypt(hdr)
        self.assertNotEqual(enc, hdr)
        self.assertEqual(b.crypt(enc), hdr)
        # WorldCrypt: same K -> identical send stream (determinism)
        c1, c3 = crypt_mod.WorldCrypt(), crypt_mod.WorldCrypt()
        c1.init(K)
        c3.init(K)
        self.assertEqual(c1.encrypt_send(hdr), c3.encrypt_send(hdr))


class TestSRP(unittest.TestCase):
    def test_interleave_length(self):
        self.assertEqual(len(srp.interleave(bytes(32))), 40)

    def test_known_vector_self_consistent(self):
        # fixed inputs -> deterministic M1/M2, no crash
        salt = bytes(range(32))
        a = 123456789
        A = srp._int_to_le(pow(srp.G_INT, a, srp.N_INT))
        B = srp._int_to_le(pow(srp.G_INT, 999999, srp.N_INT))
        K = srp.interleave(srp._int_to_le(pow(srp.G_INT, 424242, srp.N_INT)))
        m1, m2 = srp.client_proof("TESTUSER", salt, A, B, K)
        self.assertEqual(len(m1), 20)
        self.assertEqual(len(m2), 20)


class TestFactionLanguage(unittest.TestCase):
    def test_alliance_defaults_common(self):
        for race in (1, 3, 4, 7, 11):  # Human, Dwarf, NElf, Gnome, Draenei
            self.assertEqual(faction_of_race(race), "alliance")
            self.assertEqual(default_language_for_race(race), Language.COMMON)

    def test_horde_defaults_orcish(self):
        for race in (2, 5, 6, 8, 10):  # Orc, Undead, Tauren, Troll, Belf
            self.assertEqual(faction_of_race(race), "horde")
            self.assertEqual(default_language_for_race(race), Language.ORCISH)

    def test_unknown_race_safe_fallback(self):
        self.assertEqual(faction_of_race(0), "unknown")
        self.assertEqual(default_language_for_race(0), Language.COMMON)


class TestPackets(unittest.TestCase):
    def test_client_header(self):
        h = build_client_header(0x1ED, 10)
        self.assertEqual(h, struct.pack(">H", 14) + struct.pack("<I", 0x1ED))

    def test_auth_digest_matches_server_formula(self):
        import hashlib
        K = bytes(range(40))
        payload = build_auth_session("ADMIN", 0x11223344, b"\xaa\xbb\xcc\xdd",
                                     K, 1)
        # digest sits after: build(4) serverId(4) "ADMIN"(6) type(4) seed(4)
        # region(4) bg(4) realm(4) dos(8) = find via parse
        r = P.Reader(payload)
        r.u32(); r.u32(); r.cstr(); r.u32(); seed = r.raw(4)
        self.assertEqual(seed, struct.pack("<I", 0x11223344))
        r.u32(); r.u32(); r.u32(); r.u64()
        digest = r.raw(20)
        expect = hashlib.sha1(b"ADMIN" + b"\x00" * 4 + struct.pack("<I", 0x11223344)
                              + b"\xaa\xbb\xcc\xdd" + K).digest()
        self.assertEqual(digest, expect)
        # addon blob must decompress to 8 zero bytes
        blob_len = r.u32()
        blob = r.raw(blob_len)
        self.assertEqual(zlib.decompress(blob), struct.pack("<II", 0, 0))

    def _chat_payload(self, ctype=0x01, lang=7, sender_guid=0xF130000000001234,
                      channel=None, target_guid=0, text="hello"):
        w = P.Writer()
        w.u8(ctype).u32(lang).raw(P.pack_guid(sender_guid)).u32(0)
        if channel is not None:
            w.cstr(channel)
        w.raw(P.pack_guid(target_guid))
        msg = text.encode() + b"\x00"
        w.u32(len(msg)).raw(msg).u8(0)
        return w.bytes()

    def test_parse_say(self):
        line = parse_chat_packet(0x096, self._chat_payload())
        self.assertIsNotNone(line)
        assert line
        self.assertEqual(line.text, "hello")
        self.assertEqual(line.kind, "say")

    def test_parse_channel(self):
        line = parse_chat_packet(0x096, self._chat_payload(ctype=0x11, channel="World"))
        assert line
        self.assertEqual(line.channel, "World")
        self.assertEqual(line.kind, "channel")

    def test_parse_who(self):
        w = P.Writer()
        w.u32(1).u32(1)
        w.cstr("Thrall").cstr("Guild").u32(80).u32(7).u32(2).u8(0).u32(14)
        w.cstr("").cstr("")
        d = parse_who(w.bytes())
        self.assertEqual(d["entries"][0]["name"], "Thrall")

    def test_parse_channel_list(self):
        w = P.Writer()
        w.cstr("World").u8(0).u32(1)
        w.raw(P.pack_guid(123)).u8(0)
        d = parse_channel_list(w.bytes())
        self.assertEqual(d["channel"], "World")
        self.assertEqual(d["count"], 1)

    def test_join_leave_layouts(self):
        # join: u32 0, u8 0, u8 0, cstr name, cstr pass
        j = P.Writer().u32(0).u8(0).u8(0).cstr("World").cstr("").bytes()
        r = P.Reader(j)
        self.assertEqual(r.u32(), 0)
        self.assertEqual(r.u8(), 0)
        self.assertEqual(r.u8(), 0)
        self.assertEqual(r.cstr(), "World")
        # leave: u32 0, cstr name
        lv = P.Writer().u32(0).cstr("World").bytes()
        r = P.Reader(lv)
        self.assertEqual(r.u32(), 0)
        self.assertEqual(r.cstr(), "World")


if __name__ == "__main__":
    unittest.main()
