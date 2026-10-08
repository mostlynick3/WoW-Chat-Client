# ygg-chat-client

Standalone chat client for WotLK 3.3.5a (build 12340) private servers
(TrinityCore / AzerothCore / MaNGOS-compatible).

- Logs in **directly as a character** using the real game protocol
  (authserver SRP6 + worldserver `CMSG_AUTH_SESSION`, session-key ARC4 crypt).
  No WoW client needed. The character appears in-game / in who lists.
- **Web UI** served locally (`run.py` -> http://127.0.0.1:5950).
- **Desktop wrapper** (`desktop.py`) starts the same backend and opens the
  system browser (or `pywebview` window if installed), freezable with
  PyInstaller to a single executable for macOS / Windows / Linux.

Opcodes / chat types were cross-checked against
`yggdrasilcore` (`Opcodes.h`, `SharedDefines.h` `ChatMsg`,
`WorldSocket.cpp` digest + `AuthCrypt`, `ChatHandler.cpp`,
`ChannelHandler.cpp`, `Chat.cpp` `BuildChatPacket`).

## Quick start

```bash
cd ygg-chat-client
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json   # edit host/ports
python3 run.py                        # open http://127.0.0.1:5950
# or:
python3 desktop.py
```

Login is a 3-step wizard: **account** (auth host/port + credentials) ->
**realm** (picked from the live auth response, with host/port shown) ->
**character** (picked with level/race/class/faction shown) -> enter world,
exactly like a stock client: the world address always comes from the
realm list entry.

## What it does (v1)

- Auth: account login (SRP6), realm list select, world `AUTH_SESSION`,
  `CHAR_ENUM` -> character select, `PLAYER_LOGIN`.
- Chat send: Say / Yell / Emote / Party / Guild / Officer / Raid /
  RaidWarning / Battleground / Whisper / Channel.
  Language defaults to **Auto: Universal first, faction fallback**.
  Scope is stock cores + Yggdrasil: stock `ChatHandler` always rejects
  client-sent Universal for normal chat with `SMSG_NOTIFICATION`
  (`0x1CB`, "Unknown language", acore_string 805), so the client
  watches ~4s for exactly that notification and auto-resends in your
  faction tongue (Common 7 for Alliance, Orcish 1 for Horde, derived
  from your character's race). The verdict is cached per session and
  shown in the header (`universal: yes/no`); while a probe is in flight
  further sends use the safe faction tongue, so one session costs at
  most one rejected send. AFK/DND always use the faction tongue
  (stock exempts them from the Universal rejection, so probing with
  them would be meaningless). You can also force a tongue
  (Common/Orcish/Universal) from the dropdown — forced sends never
  fall back.
- Chat receive: `SMSG_MESSAGECHAT` + `SMSG_GM_MESSAGECHAT` tolerant parser
  (packed GUIDs, channel + GM variants).
- Channels: join (`channel+password`), leave, list members,
  channel notices (`SMSG_CHANNEL_NOTIFY`).
- Roster: `/who` (`CMSG_WHO`/`SMSG_WHO`), name lookup.
- Logout: `CMSG_LOGOUT_REQUEST` + clean socket close; backend also
  supports full disconnect.
- Keepalive: `CMSG_PING` every ~30s, `CMSG_KEEP_ALIVE` handling.

## Layout

```
run.py            local web server entry
desktop.py        desktop wrapper entry (browser/pywebview)
config.example.json
app/server.py     Flask REST API (polling, no WS dependency)
app/wow_client.py high-level WoW connection manager (threaded)
wow/srp.py        SRP6 client (WoW variant, k=3, SHA1Interleave)
wow/crypt.py      ARC4-drop1024 world crypt (AuthCrypt-compatible)
wow/protocol.py   packet reader/writer helpers (C-string, packed GUID)
wow/opcodes.py    opcodes pinned to yggdrasilcore Opcodes.h
wow/chat_defs.py  ChatMsg + languages + channel-notify enums
wow/auth_socket.py  authserver (3724) login + realm list
wow/world_socket.py worldserver login + chat/channel/who/logout loop
web/              static UI (index.html/app.js/style.css)
tests/            offline unit tests (no server needed)
build/            PyInstaller build scripts
```

## Config

See `config.example.json`. Per-login you can override host/ports/realm/
character from the UI; config file only provides defaults.

## Security notes

- Credentials live only in memory; never written to disk by the app.
- Session key `K` is kept in-process and zeroed on logout/disconnect.
- Use a dedicated low-privilege account; the client identifies as a
  normal `Win`/`x86` 3.3.5a client.
- Some servers enforce client CRC / Warden / IP lock / GEO lock; if
  login fails with `AUTH_FAILED` check those server-side settings.

## Limitations

- Chat-only: no movement, combat, spells, or world rendering.
- `SAY`/`YELL` are proximity-based server-side; you only *receive* them
  if the character is near the speaker (same as in-game).
- See `README` sections in `app/` + `wow/` for packet-level details.
