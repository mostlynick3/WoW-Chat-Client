# ygg-chat-client

Standalone chat client for WotLK 3.3.5a (build 12340) private servers
(TrinityCore / AzerothCore / MaNGOS-compatible).

- **Full character auth**: Logs in as a normal character using the real game protocol
  (authserver SRP6 + worldserver `CMSG_AUTH_SESSION`, session-key ARC4 crypt).
  No WoW client needed. The character appears in-game / in who lists.
- **Web hostable**: Can be web hosted and run locally or remotely at your will (`run.py` -> http://127.0.0.1:5950).
- **Desktop app**: Every commit creates a new pre-compield executable for macOS / Windows / Linux.

Opcodes / chat types were cross-checked against
`yggdrasilcore` (`Opcodes.h`, `SharedDefines.h` `ChatMsg`,
`WorldSocket.cpp` digest + `AuthCrypt`, `ChatHandler.cpp`,
`ChannelHandler.cpp`, `Chat.cpp` `BuildChatPacket`).

## Quick start
Choose option 1 or 2 below:

1. Use the direct app for your OS [here](https://github.com/mostlynick3/WoW-Chat-Client/releases/tag/continuous). We recommend AppImage
for all Linux distros.
Alternatively, you may download the source code [here](https://github.com/mostlynick3/WoW-Chat-Client/archive/refs/heads/main.zip) and run the below commands directly for CLI control.
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 desktop.py
```

2. Use the plug-and-play Linux web server from [here](https://github.com/mostlynick3/WoW-Chat-Client/releases/tag/continuous), or run the web server directly on a system of your choice by the below instructions, then connect to it on port 5950 from any browser.
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json   # edit host/ports
python3 run.py              
# open http://127.0.0.1:5950 from any browser
```

## How does it work?
Login is a 3-step wizard: **account** -> **realm** -> **character** (picked with level/race/class/faction
shown) -> enter world, exactly like a stock client.
<img width="1100" height="778" alt="image" src="https://github.com/user-attachments/assets/5148f0d0-e7f0-4b1d-9f74-edc687583c3d" />
<img width="599" height="360" alt="image" src="https://github.com/user-attachments/assets/54de7908-4864-4f55-9986-f0dde10e5e17" />
<img width="1117" height="573" alt="image" src="https://github.com/user-attachments/assets/4f155681-3add-4f4e-8260-4d66fe0f5052" />


## If auth fails

Every step is logged to browser JS console. For full debug, run the web
server and open it in a browser of your choice. Typical causes for auth fail:

- `cannot resolve '...'` / DNS timeout — wrong hostname or no DNS.
- `connection refused ... not listening there?` — wrong host/port or
  the authserver is down.
- `closed the connection while: logon-challenge reply` — the server
  hung up without answering (packet rejected, IP-filtered, or not a
  3.3.5a authserver at all).
- `WOW_FAIL_UNKNOWN_ACCOUNT` on the challenge — account name doesn't
  exist. The same code on the **proof** step means the password is
  wrong (each login attempt with a wrong password is also logged
  server-side, and repeated failures can trigger `WrongPass` IP bans —
  check `authserver.conf`).
- `WOW_FAIL_VERSION_INVALID` — build rejected (`AcceptedClientBuilds`
  server-side, or `StrictVersionCheck` with a zero exe CRC).
- `... timed out after Ns` — the server stalled mid-handshake; phases
  have hard deadlines so a hung server can never hang the UI forever.

## What it does (v1)

- Auth: account login (SRP6), realm list select, world `AUTH_SESSION`,
  `CHAR_ENUM` -> character select, `PLAYER_LOGIN`.
- Chat send: Say / Yell / Emote / Party / Guild / Officer / Raid /
  RaidWarning / Battleground / Whisper / Channel.
  Language defaults to **Auto: your faction tongue** (Common 7 for
  Alliance, Orcish 1 for Horde, derived from your character's race).
  The server logs a hacking-attempt for client-sent Universal, so Auto
  never sends it; you can still force Universal from the dropdown, and a
  forced Universal rejected with stock `SMSG_NOTIFICATION` "Unknown
  language" (`0x1CB`, acore_string 805) is auto-resent once in your
  faction tongue. The verdict is shown in the header
  (`universal: yes/no`).
- Chat receive: `SMSG_MESSAGECHAT` + `SMSG_GM_MESSAGECHAT` parsed per
  `BuildChatPacket` (full u64 guids, GM/channel/monster variants).
  `LANG_ADDON` traffic (anticheat/addon pings) is filtered out of the
  feed like a stock client. Player guids resolve to names in the
  background via `CMSG_NAME_QUERY`.
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
- See `README` sections in `app/` + `wow/` for packet-level details.

## Releases (CI)

Every push to `main` runs `.github/workflows/release.yml`: PyInstaller
builds the server binary (Linux) plus the desktop binaries (Linux,
Windows, macOS) and publishes them on the rolling **`continuous`**
prerelease. The distributed binaries are the desktop ones; the server
binary is for headless use.

## License

Copyright (C) 2026 mostlynick3

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License version 2 as published
by the Free Software Foundation. See `LICENSE` for the full text.

## Graphics and intellectual property

All graphics and artwork bundled or referenced by this client are the
property of their respective owners. This repository lays no claim to
copyright over Blizzard Entertainment material, including World of
Warcraft, nor over the intellectual property or graphics of any of the
servers included in the server list. Server logos and artwork are bundled
locally for display in the login screen only.
