"""WoW-flavoured SRP6 client.

Mirrors yggdrasilcore src/common/Cryptography/Authentication/SRP6.cpp:
  N = 894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7
  g = 7, k = 3  (B = g^b + 3*v mod N)
  x = SHA1(s | SHA1(UPPER(user) + ":" + UPPER(pass)))
  u = SHA1(A_wire | B_wire) as integer (wire = 32-byte little-endian)
  S = (B - 3*g^x) ^ (a + u*x) mod N
  K = SHA1Interleave(S)  (even/odd byte split, see server code)
  M1 = SHA1(H(N) xor H(g), H(I), s, A, B, K)
  M2 = SHA1(A, M1, K)

All 32-byte integers on the wire are little-endian. Hash inputs use the
exact wire bytes. Username/password are uppercased (latin) like the core.
"""
from __future__ import annotations

import hashlib
import secrets

N_HEX_BE = "894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7"
N_INT = int(N_HEX_BE, 16)
G_INT = 7
K_MULT = 3
KEY_LEN = 32

# Server stores N reversed (little-endian) for H(N); replicate exactly.
N_LE = bytes.fromhex(N_HEX_BE)[::-1]
G_BYTE = b"\x07"


def _sha1(*parts: bytes) -> bytes:
    h = hashlib.sha1()
    for p in parts:
        h.update(p)
    return h.digest()


def _int_to_le(n: int, length: int = 32) -> bytes:
    return n.to_bytes(length, "little")


def _le_to_int(b: bytes) -> int:
    return int.from_bytes(b, "little")


def upper_latin(s: str) -> str:
    # Core uses Utf8ToUpperOnlyLatin; ascii upper is the compatible subset.
    return "".join(chr(ord(c) - 32) if "a" <= c <= "z" else c for c in s)


def compute_x(salt_le: bytes, username: str, password: str) -> int:
    up = upper_latin(username) + ":" + upper_latin(password)
    inner = _sha1(up.encode("utf-8"))
    # BigNumber(SHA1 digest) is big-endian (openssl BN_bin2bn semantics).
    return int.from_bytes(_sha1(salt_le, inner), "big")


def compute_verifier_for_test(salt_le: bytes, username: str, password: str) -> bytes:
    # v = g^x mod N (wire little-endian). Server hashes x as big-endian
    # BigNumber (SHA1 digest -> BigNumber is big-endian); keep that here.
    x = compute_x(salt_le, username, password)
    return _int_to_le(pow(G_INT, x, N_INT))


def interleave(S_le: bytes) -> bytes:
    if len(S_le) != 32:
        S_le = S_le.rjust(32, b"\x00")[-32:]
    buf0 = bytes(S_le[0::2])
    buf1 = bytes(S_le[1::2])
    # first nonzero byte logic from SRP6::SHA1Interleave (S is LE array)
    p = 0
    while p < 32 and S_le[p] == 0:
        p += 1
    if p & 1:
        p += 1
    p //= 2
    h0 = _sha1(buf0[p:])
    h1 = _sha1(buf1[p:])
    out = bytearray(40)
    for i in range(20):
        out[2 * i] = h0[i]
        out[2 * i + 1] = h1[i]
    return bytes(out)


def ng_hash() -> bytes:
    nh = _sha1(N_LE)
    gh = _sha1(G_BYTE)
    return bytes(a ^ b for a, b in zip(nh, gh))


def client_proof(username: str, salt_le: bytes, A_le: bytes, B_le: bytes, K: bytes):
    h_i = _sha1(upper_latin(username).encode("utf-8"))
    m1 = _sha1(ng_hash(), h_i, salt_le, A_le, B_le, K)
    m2 = _sha1(A_le, m1, K)
    return m1, m2


def generate_client_ephemeral() -> tuple[int, bytes]:
    # 19 random bytes like the core server-side; 32 is also fine. Use 32.
    a = int.from_bytes(secrets.token_bytes(32), "big") % N_INT
    if a == 0:
        a = 1
    A_le = _int_to_le(pow(G_INT, a, N_INT))
    return a, A_le


def compute_session_key(
    a: int, A_le: bytes, B_le: bytes, salt_le: bytes, username: str, password: str
) -> tuple[bytes, bytes]:
    B = _le_to_int(B_le)
    x = compute_x(salt_le, username, password)
    gx = pow(G_INT, x, N_INT)
    # S = (B - 3*g^x) ^ (a + u*x) mod N
    u = int.from_bytes(_sha1(A_le, B_le), "big")
    base = (B - K_MULT * gx) % N_INT
    exp = (a + u * x) % (N_INT - 1)
    S_int = pow(base, exp, N_INT)
    S_le = _int_to_le(S_int)
    K = interleave(S_le)
    m1, m2_expected = client_proof(username, salt_le, A_le, B_le, K)
    return K, m1
