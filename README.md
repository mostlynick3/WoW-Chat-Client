# <img src="build/appimage/WoW-Chat-Client.png" width="56"> WoW Chat Client

Chat with your characters on any WotLK 3.3.5a private server — no game
client needed. Log in as a real character and talk in guild, party,
channels and whispers, from the app or any browser.

<p align="center">
<a href="https://github.com/mostlynick3/WoW-Chat-Client/releases/download/continuous/wow-chat-desktop-windows.exe"><img src="docs/icons/windows8.svg" width="48" alt="Windows"></a>&nbsp;&nbsp;
<a href="https://github.com/mostlynick3/WoW-Chat-Client/releases/download/continuous/WoW-Chat-Client-linux-x86_64.AppImage"><img src="docs/icons/linux.svg" width="48" alt="Linux"></a>&nbsp;&nbsp;
<a href="https://github.com/mostlynick3/WoW-Chat-Client/releases/download/continuous/wow-chat-desktop-macos"><img src="docs/icons/apple.svg" width="48" alt="macOS"></a>&nbsp;&nbsp;
<a href="https://github.com/mostlynick3/WoW-Chat-Client/releases/download/continuous/wow-chat-android.apk"><img src="docs/icons/android.svg" width="48" alt="Android"></a>&nbsp;&nbsp;
<a href="#run-it-on-your-own-server"><img src="docs/icons/apache.svg" width="48" alt="Self-hosted web"></a>
</p>

Click an icon above for the latest build (rebuilt on every commit), or
[see all files](https://github.com/mostlynick3/WoW-Chat-Client/releases/tag/continuous).

## What you can do

- Log in as any of your characters: account → realm → character, just
  like the game client.
- Chat everywhere: Say, Yell, Party, Guild, Officer, Raid, Battleground,
  Whisper, and custom channels.
- Speak your faction tongue automatically (Common / Orcish by race), or
  force another tongue.
- Join and leave channels, see who's in them, `/who` search across the
  server.
- Works on any 3.3.5a server that accepts stock client connections.

<p align="center">
<img width="1100" height="778" alt="Login, realm and character screens" src="https://github.com/user-attachments/assets/5148f0d0-e7f0-4b1d-9f74-edc687583c3d" />
<img width="599" height="360" alt="Chat window" src="https://github.com/user-attachments/assets/54de7908-4864-4f55-9986-f0dde10e5e17" />
<img width="1117" height="573" alt="Channel and who list" src="https://github.com/user-attachments/assets/4f155681-3add-4f4e-8260-4d66fe0f5052" />
</p>

## Run it on your own server

Prefer hosting it yourself? Grab `wow-chat-server-linux` from the
release, or run from source on any machine and open
`http://<your-server>:5950` from any browser — desktop or phone.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 desktop.py   # app window — or: python3 run.py  (browser UI on :5950)
```

Your account password is only ever used for the login handshake, kept in
memory, and wiped on logout — never written to disk.

## If login fails

- `cannot resolve ...` — wrong hostname or no DNS.
- `connection refused` — wrong host/port, or the authserver is down.
- Unknown account vs wrong password: a bad name fails fast, a bad
  password fails at the proof step. Note some servers answer both the
  same way — and repeated wrong passwords can trigger `WrongPass` IP
  bans server-side.
- `WOW_FAIL_VERSION_INVALID` — the server rejects this client build
  (`AcceptedClientBuilds` / `StrictVersionCheck` server-side).

## Limitations

- Chat-only: no movement, combat, spells, or world rendering.

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
