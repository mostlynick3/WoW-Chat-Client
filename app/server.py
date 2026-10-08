"""Flask REST backend. Polling only (no websocket dependency).

  GET  /api/status                 connection snapshot
  GET  /api/realms                 last realm list
  GET  /api/messages?since_id=N   new chat lines
  POST /api/auth                   {auth_host,auth_port,username,password}
                                   -> {realms:[{id,name,address}]}
  POST /api/characters             {realm_id}
                                   -> {characters:[{name,level,race,class}]}
  POST /api/enter                  {character_name} -> enter world
  POST /api/send                   {kind,say|yell|...,text,target,channel,lang}
  POST /api/join  {name,password}  POST /api/leave {name}
  POST /api/chanlist {name}        POST /api/who {...}
  POST /api/logout                 POST /api/disconnect
  GET  /                           serves web/index.html
"""
from __future__ import annotations

import json
import os
import sys

from flask import Flask, jsonify, request, send_from_directory

from .wow_client import WoWChatManager
from wow.chat_defs import CLASS_COLORS, RACE_LANGUAGES, ZONE_NAMES, language_name

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE = sys._MEIPASS  # type: ignore[attr-defined]
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(BASE, "web")

app = Flask(__name__)
mgr = WoWChatManager()


@app.get("/api/meta")
def meta():
    # Display maps (single source of truth for the UI).
    return jsonify({
        "zones": {str(k): v for k, v in ZONE_NAMES.items()},
        "class_colors": {str(k): v for k, v in CLASS_COLORS.items()},
        "realm_types": {"0": "Normal", "1": "PvP", "4": "Normal",
                        "6": "RP", "8": "RPPvP"},
        "race_languages": {str(r): list(l) for r, l in RACE_LANGUAGES.items()},
        "language_names": {str(l): language_name(l) for l in
                           {x for t in RACE_LANGUAGES.values() for x in t}},
    })


@app.get("/api/status")
def status():
    snap = mgr.snapshot()
    snap["debug"] = mgr.debug_tail(40)
    return jsonify(snap)


@app.get("/api/realms")
def realms():
    return jsonify({"realms": mgr.realms})


@app.get("/api/messages")
def messages():
    since = int(request.args.get("since_id", 0))
    return jsonify({"messages": mgr.get_messages(since)})


@app.post("/api/auth")
def auth():
    """Phase 1: credentials -> realm list (no manual realm id needed)."""
    body = request.get_json(force=True) or {}
    res = mgr.fetch_realms(
        auth_host=body.get("auth_host", "127.0.0.1"),
        auth_port=int(body.get("auth_port", 3724)),
        username=body.get("username", ""),
        password=body.get("password", ""),
        token=str(body.get("token", "") or ""),
    )
    return jsonify(res)


@app.post("/api/characters")
def characters():
    """Phase 2: chosen realm id -> character list."""
    body = request.get_json(force=True) or {}
    return jsonify(mgr.fetch_characters(realm_id=int(body.get("realm_id", 0))))


@app.post("/api/enter")
def enter():
    """Phase 3: chosen character -> enter world."""
    body = request.get_json(force=True) or {}
    return jsonify(mgr.enter_world(body.get("character_name", "") or ""))


@app.post("/api/send")
def send():
    body = request.get_json(force=True) or {}
    lang = body.get("lang", "auto")  # "auto" | number | "universal"
    if isinstance(lang, str) and lang not in ("auto", "universal"):
        try:
            lang = int(lang)
        except ValueError:
            lang = "auto"
    if lang == "universal":
        lang = 0
    elif lang is not None and lang != "auto":
        lang = int(lang)
    return jsonify(mgr.send(
        kind=body.get("kind", "say"),
        text=body.get("text", ""),
        target=body.get("target", "") or "",
        channel=body.get("channel", "") or "",
        lang=lang,
    ))


@app.post("/api/join")
def join():
    body = request.get_json(force=True) or {}
    return jsonify(mgr.join(body.get("name", ""), body.get("password", "")))


@app.post("/api/leave")
def leave():
    body = request.get_json(force=True) or {}
    return jsonify(mgr.leave(body.get("name", "")))


@app.post("/api/chanlist")
def chanlist():
    body = request.get_json(force=True) or {}
    return jsonify(mgr.chan_list(body.get("name", "")))


@app.post("/api/who")
def who():
    body = request.get_json(force=True) or {}
    allowed = ("name_sub", "zone_sub", "min_level", "max_level",
               "race_mask", "class_mask")
    kw = {k: body[k] for k in allowed if k in body}
    return jsonify(mgr.who(**kw))


@app.get("/api/who_result")
def who_result():
    """Latest /who answer for the Who modal (not the chat feed)."""
    return jsonify(mgr.who_result())


@app.get("/api/chan_result")
def chan_result():
    """Latest channel-member answer for the Channel modal."""
    return jsonify(mgr.chan_result())


@app.post("/api/logout")
def logout():
    return jsonify(mgr.logout())


@app.post("/api/disconnect")
def disconnect():
    mgr.disconnect()
    return jsonify({"ok": True})


@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/<path:path>")
def static_files(path: str):
    # only serve known web assets, never arbitrary paths
    if os.path.basename(path) in ("app.js", "icons.js", "style.css",
                                   "index.html", "favicon.ico"):
        return send_from_directory(WEB, os.path.basename(path))
    if path.startswith("assets/"):
        name = os.path.basename(path)
        if name in ("slide-04.jpg", "MORPHEUS.ttf", "chromiecraft.png",
                    "truewow.png", "risinggods.png"):
            return send_from_directory(os.path.join(WEB, "assets"), name)
    return jsonify({"error": "not found"}), 404


def load_defaults() -> dict:
    for name in ("config.json", "config.example.json"):
        p = os.path.join(BASE, name)
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    return {}
