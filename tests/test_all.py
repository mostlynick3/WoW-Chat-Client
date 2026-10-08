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
    language_name,
)
from wow.world_socket import parse_notification

from app.wow_client import WoWChatManager
from wow import net as netmod
from wow.auth_socket import build_logon_challenge, parse_realm_blob
from wow.world_socket import parse_char_enum
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

    def test_x_is_little_endian_like_server(self):
        # Server BigNumber(byte-array) defaults to littleEndian=true.
        import hashlib as _hl
        salt = bytes(range(32))
        d = _hl.sha1(salt + _hl.sha1(b"U:P").digest()).digest()
        self.assertEqual(srp.compute_x(salt, "u", "p"),
                         int.from_bytes(d, "little"))

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

    def test_language_names(self):
        self.assertEqual(language_name(0), "Universal")
        self.assertEqual(language_name(1), "Orcish")
        self.assertEqual(language_name(7), "Common")


class FakeWorld:
    def __init__(self):
        self.sent: list[tuple] = []

    def send_chat(self, ctype, lang, text, target="", channel=""):
        self.sent.append((ctype, lang, text, target, channel))


class TestUniversalProbe(unittest.TestCase):
    def _mgr(self):
        m = WoWChatManager()
        m.state = "online"
        m.language = 1  # Horde -> Orcish fallback
        m.world = FakeWorld()
        return m

    def test_auto_probes_universal_first(self):
        m = self._mgr()
        tongue, probe = m.resolve_lang("auto")
        self.assertEqual((tongue, probe), (0, True))

    def test_second_send_while_probing_uses_faction_tongue(self):
        m = self._mgr()
        m._probes.append({"ts": __import__("time").time(), "ctype": 1,
                          "text": "hi", "target": "", "channel": ""})
        self.assertEqual(m.resolve_lang("auto"), (1, False))

    def test_rejection_resends_in_faction_tongue(self):
        m = self._mgr()
        r = m.send("say", "hello")
        self.assertTrue(r["ok"] and r["probed"])
        self.assertEqual(m.world.sent[-1][1], 0)
        m._on_notification("Unknown language")
        self.assertFalse(m.universal_verdict)
        self.assertEqual(m.world.sent[-1][1], 1)  # resent Orcish
        self.assertEqual(m.world.sent[-1][2], "hello")
        # verdict cached: no more probing
        self.assertEqual(m.resolve_lang("auto"), (1, False))

    def test_unrelated_notification_ignored(self):
        m = self._mgr()
        m.send("say", "hello")
        m._on_notification("You must wait a while before speaking.")
        self.assertIsNone(m.universal_verdict)
        self.assertEqual(len(m.world.sent), 1)

    def test_rejection_match_is_exact_stock_string(self):
        m = self._mgr()
        m.send("say", "hello")
        m._on_notification("Unknown languages!")  # near-miss: no fallback
        self.assertIsNone(m.universal_verdict)
        self.assertEqual(len(m.world.sent), 1)
        m._on_notification("  Unknown Language ")  # case/space: fallback
        self.assertFalse(m.universal_verdict)
        self.assertEqual(m.world.sent[-1][1], 1)

    def test_afk_dnd_never_probe(self):
        m = self._mgr()
        for kind in ("afk", "dnd"):
            r = m.send(kind, "brb")
            self.assertTrue(r["ok"] and not r["probed"])
            self.assertEqual(r["lang"], 1)
        self.assertEqual(m.resolve_lang("auto", "afk"), (1, False))

    def test_silence_means_accepted(self):
        import time as _t
        m = self._mgr()
        m.send("say", "hello")
        m._probes[0]["ts"] -= 10  # age past PROBE_WINDOW
        m._settle_probes()
        self.assertTrue(m.universal_verdict)
        self.assertEqual(m.resolve_lang("auto"), (0, False))

    def test_forced_tongue_never_probes(self):
        m = self._mgr()
        self.assertEqual(m.resolve_lang(7), (7, False))
        self.assertEqual(m.resolve_lang(0), (0, False))

    def test_notification_parse(self):
        self.assertEqual(parse_notification(b"Unknown language\x00"),
                         "Unknown language")


class FakeAuthClient:
    def __init__(self, host, port=3724, timeout=8.0, log=None):
        self.session_key = None
        self.closed = False

    def logon(self, username, password):
        if password != "right":
            raise PermissionError("auth proof failed")
        self.session_key = bytes(range(40))

    def realm_list(self):
        from collections import namedtuple
        R = namedtuple("R", ["id", "name", "address", "population"])
        return [R(1, "Azeroth", "10.0.0.5:8085", 0.5),
                R(2, "Northrend", "10.0.0.6:8085", 1.0)]

    def close(self):
        self.closed = True


class FakeWorldClient:
    def __init__(self):
        from wow.world_socket import CharacterInfo
        self.characters = [CharacterInfo(guid=1001, name="Thrall", level=80,
                                         race=2, cls=7),
                           CharacterInfo(guid=1002, name="Jaina", level=80,
                                         race=1, cls=8)]
        self.logged_in = None

    def connect(self, host, port):
        self.addr = (host, port)

    def login(self, account, key, realm_id):
        self.logged_in = (account, realm_id)

    def player_login(self, guid):
        self.entered = guid

    def close(self):
        pass


class TestLoginWizard(unittest.TestCase):
    def _mgr(self):
        import app.wow_client as wc
        self._orig_auth, self._orig_world = wc.AuthClient, wc.WorldClient
        wc.AuthClient = FakeAuthClient
        wc.WorldClient = FakeWorldClient
        m = wc.WoWChatManager()
        m.state = "offline"
        self.addCleanup(setattr, wc, "AuthClient", self._orig_auth)
        self.addCleanup(setattr, wc, "WorldClient", self._orig_world)
        return m

    def test_auth_returns_realm_choice(self):
        m = self._mgr()
        r = m.fetch_realms("h", 3724, "user", "right")
        self.assertTrue(r["ok"])
        self.assertEqual([x["name"] for x in r["realms"]],
                         ["Azeroth", "Northrend"])
        self.assertEqual(m.state, "realms")
        # password must not be retained anywhere
        self.assertNotIn("right", repr(m.__dict__))

    def test_auth_bad_password(self):
        m = self._mgr()
        r = m.fetch_realms("h", 3724, "user", "wrong")
        self.assertFalse(r["ok"])
        self.assertEqual(m.state, "offline")

    def test_realm_to_characters_to_enter(self):
        m = self._mgr()
        m.fetch_realms("h", 3724, "user", "right")
        r = m.fetch_characters(2)
        self.assertTrue(r["ok"])
        self.assertEqual([c["name"] for c in r["characters"]],
                         ["Thrall", "Jaina"])
        self.assertIn("10.0.0.6", r["realm"])
        # Horde pick -> Orcish fallback tongue
        r = m.enter_world("Thrall")
        self.assertTrue(r["ok"])
        self.assertEqual((m.character, m.faction, m.language),
                         ("Thrall", "horde", 1))
        self.assertEqual(m.state, "online")

    def test_unknown_realm_rejected(self):
        m = self._mgr()
        m.fetch_realms("h", 3724, "user", "right")
        r = m.fetch_characters(99)
        self.assertFalse(r["ok"])


def _realm_entry(flags: int = 0) -> bytes:
    import struct as _st
    e = bytes([1, 0, flags]) + b"Azeroth\x00" + b"10.0.0.5:8085\x00"
    e += _st.pack("<f", 0.5) + bytes([3, 14, 1])
    if flags & 0x04:
        e += bytes([3, 3, 5]) + _st.pack("<H", 12340)
    return e


def _realm_blob(flags: int = 0) -> bytes:
    return _realm_entry(flags) + bytes([0x10, 0x00])


class TestChallengePacket(unittest.TestCase):
    def test_size_invariant(self):
        # Server closes the connection with no reply unless
        # size - 30 == I_len (AuthSession::HandleLogonChallenge).
        import struct as _st
        for name in ("METALLINOS5", "x", "a" * 16):
            pkt = build_logon_challenge(name)
            self.assertEqual(pkt[0], 0x00)
            size = _st.unpack_from("<H", pkt, 2)[0]
            self.assertEqual(len(pkt), 4 + size)
            body = pkt[4:]
            self.assertEqual(size, len(body))
            i_len = body[29]
            self.assertEqual(size - 30, i_len)
            self.assertEqual(body[30:30 + i_len],
                             name.upper().encode("ascii"))
            # "metallinos5" is 11 chars -> 45 bytes total, not 46
            if name == "METALLINOS5":
                self.assertEqual(len(pkt), 45)


def _char_bytes(guid: int, name: str, race: int, cls: int,
                level: int) -> bytes:
    import struct as _st
    b = _st.pack("<Q", guid) + name.encode() + b"\x00"
    b += bytes([race, cls, 0, 0, 0, 0, 0, 0, level])
    b += _st.pack("<IIfff", 14, 571, 1.0, 2.0, 3.0)
    b += _st.pack("<III", 0, 0, 0)  # guild, charFlags, customize
    b += bytes([0])  # first login
    b += _st.pack("<III", 0, 0, 0)  # pet
    b += (_st.pack("<IBI", 0, 0, 0)) * 23  # equipment
    return b


class TestCharEnum(unittest.TestCase):
    def test_two_chars_stay_aligned(self):
        # Regression: missing customize u32 + wrong equip count desynced
        # every character after the first.
        blob = (bytes([2]) + _char_bytes(1001, "Thrall", 2, 7, 80)
                + _char_bytes(1002, "Jaina", 1, 8, 80))
        out = parse_char_enum(blob)
        self.assertEqual([(c.guid, c.name, c.race, c.cls, c.level)
                          for c in out],
                         [(1001, "Thrall", 2, 7, 80),
                          (1002, "Jaina", 1, 8, 80)])


class TestRealmBlob(unittest.TestCase):
    def test_plain_entry(self):
        out = parse_realm_blob(_realm_blob(), 1)
        self.assertEqual([(r.id, r.name, r.address) for r in out],
                         [(1, "Azeroth", "10.0.0.5:8085")])

    def test_specifybuild_extra_bytes_skipped(self):
        blob = _realm_entry(0x04) + _realm_entry() + bytes([0x10, 0x00])
        out = parse_realm_blob(blob, 2)
        self.assertEqual([r.name for r in out], ["Azeroth", "Azeroth"])


class TestNet(unittest.TestCase):
    def test_literal_ip_no_dns(self):
        self.assertEqual(netmod.resolve_ipv4("127.0.0.1"), "127.0.0.1")

    def test_unresolvable_host_fast_error(self):
        with self.assertRaises((ConnectionError, TimeoutError)):
            netmod.resolve_ipv4("nonexistent.invalid", timeout=5)


class TestGuarded(unittest.TestCase):
    def test_deadline(self):
        import time as _t
        with self.assertRaises(TimeoutError):
            WoWChatManager._run_guarded(lambda: _t.sleep(5), 0.2, "test op")

    def test_passthrough(self):
        self.assertEqual(
            WoWChatManager._run_guarded(lambda: 42, 5.0, "test op"), 42)


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
        import struct as _st
        w = P.Writer()
        w.u8(ctype).u32(lang).u64(sender_guid).u32(0)
        if channel is not None:
            w.cstr(channel)
        w.u64(target_guid)
        msg = text.encode() + b"\x00"
        w.u32(len(msg)).raw(msg).u8(0)
        return w.bytes()

    def test_parse_say(self):
        line = parse_chat_packet(0x096, self._chat_payload())
        self.assertIsNotNone(line)
        assert line
        self.assertEqual(line.text, "hello")
        self.assertEqual(line.kind, "say")
        self.assertEqual(line.sender_guid, 0xF130000000001234)

    def test_parse_channel(self):
        line = parse_chat_packet(0x096, self._chat_payload(ctype=0x11, channel="World"))
        assert line
        self.assertEqual(line.channel, "World")
        self.assertEqual(line.kind, "channel")

    def test_live_anticheat_addon_packet(self):
        # Captured on Yggdrasil QA: server anticheat addon ping. guids
        # are FULL u64 (sender == target == player guid 341 here).
        raw = bytes.fromhex(
            "07ffffffff550100000000000000000000550100000000000014000000"
            "41494f5f416e746943686561740966616c73650000")
        line = parse_chat_packet(0x096, raw)
        assert line
        self.assertEqual(line.kind, "whisper")
        self.assertEqual(line.lang, 0xFFFFFFFF)
        self.assertEqual(line.sender_guid, 341)
        self.assertEqual(line.target_guid, 341)
        self.assertEqual(line.text, "AIO_AntiCheat\tfalse")

    def test_parse_who(self):
        w = P.Writer()
        w.u32(1).u32(1)
        w.cstr("Thrall").cstr("Guild").u32(80).u32(7).u32(2).u8(0).u32(14)
        w.cstr("").cstr("")
        d = parse_who(w.bytes())
        self.assertEqual(d["entries"][0]["name"], "Thrall")

    def test_parse_channel_list(self):
        import struct as _st
        w = P.Writer()
        w.u8(1).cstr("World").u8(0).u32(1)
        w.u64(123).u8(0)
        d = parse_channel_list(w.bytes())
        self.assertEqual(d["channel"], "World")
        self.assertEqual(d["count"], 1)
        self.assertEqual(d["members"][0]["guid"], 123)

    def test_name_query_parse(self):
        import struct as _st
        blob = _st.pack("<Q", 341) + bytes([0]) + b"Nickee\x00"
        from wow.world_socket import parse_name_query
        d = parse_name_query(blob)
        self.assertEqual((d["guid"], d["name"]), (341, "Nickee"))


class TestManagerNamesAndAddonFilter(unittest.TestCase):
    def _mgr(self):
        m = WoWChatManager()
        m.state = "online"
        m.language = 1
        m.world = FakeWorld()
        return m

    def test_addon_chatter_never_reaches_feed(self):
        import time as _t
        from wow.world_socket import ChatLine
        m = self._mgr()
        m._push_line(ChatLine(ts=_t.time(), opcode=0x96, ctype=7,
                              kind="whisper", sender="", channel="",
                              text="AIO_AntiCheat\tfalse",
                              lang=0xFFFFFFFF, sender_guid=341))
        self.assertEqual(m.get_messages(), [])
        self.assertEqual(m.addon_dropped, 1)

    def test_sender_name_resolved_via_query(self):
        import time as _t
        from wow.world_socket import ChatLine
        m = self._mgr()
        m._push_line(ChatLine(ts=_t.time(), opcode=0x96, ctype=1,
                              kind="say", sender="", channel="",
                              text="hello", lang=7, sender_guid=341))
        msgs = m.get_messages()
        self.assertEqual(msgs[0]["sender"], "guid:341")
        m._on_name_query({"guid": 341, "name": "Nickee"})
        msgs = m.get_messages()
        self.assertEqual(msgs[0]["sender"], "Nickee")

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
