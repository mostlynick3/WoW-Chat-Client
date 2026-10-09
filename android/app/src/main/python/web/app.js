"use strict";
let sinceId = 0, online = false, pollTimer = null, lastDebugTs = 0;
let pickedRealm = 0, pickedChar = "";

const $ = (id) => document.getElementById(id);
const feed = $("feed");

const RACES = { 1: "Human", 2: "Orc", 3: "Dwarf", 4: "Night Elf", 5: "Undead",
  6: "Tauren", 7: "Gnome", 8: "Troll", 10: "Blood Elf", 11: "Draenei" };
const CLASSES = { 1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest",
  6: "Death Knight", 7: "Shaman", 8: "Mage", 9: "Warlock", 11: "Druid" };
const ALLY_RACES = new Set([1, 3, 4, 7, 11]);
const factionOf = (r) => ALLY_RACES.has(r) ? "alliance" : "horde";

/* preset servers (auth port 3724 unless overridden via Manual entry) */
const SERVERS = {
  yggdrasil: { label: "Yggdrasil", host: "logon.yggdrasilwow.com", port: 3724 },
  truewow: { label: "TrueWoW", host: "login.truewow.org", port: 3724 },
  chromiecraft: { label: "ChromieCraft", host: "logon.chromiecraft.com", port: 3724 },
  risinggods: { label: "Rising Gods", host: "logon.rising-gods.de", port: 3724 },
};
function selectedServer() {
  const v = $("serverPick").value;
  if (v === "manual") {
    return { label: "Custom",
      host: $("authHost").value.trim(),
      port: +$("authPort").value || 3724 };
  }
  return SERVERS[v] || SERVERS.yggdrasil;
}
$("serverPick").addEventListener("change", () => {
  const manual = $("serverPick").value === "manual";
  $("manualBox").classList.toggle("hidden", !manual);
  syncBranding();
  syncTitle();
  try { localStorage.setItem("ygg_server", $("serverPick").value); } catch { }
});
/* Page title always names the server: "<label> - WoW Chat".
   Presets use their shorthand label; manual entry uses the typed
   auth address (host[:port]), falling back to "Custom" when empty. */
function syncTitle() {
  const srv = selectedServer();
  let name = srv.label;
  if ($("serverPick").value === "manual") {
    name = srv.host ? srv.host + (srv.port !== 3724 ? ":" + srv.port : "")
                    : "Custom";
  }
  document.title = `${name} - WoW Chat`;
}
for (const id of ["authHost", "authPort"])
  $(id).addEventListener("input", syncTitle);
/* Per-server branding: artwork behind the login frame. */
function syncBranding() {
  const v = $("serverPick").value;
  const lv = $("loginView");
  lv.classList.toggle("ygg", v === "yggdrasil");
  lv.classList.toggle("cc", v === "chromiecraft");
  lv.classList.toggle("tw", v === "truewow");
  lv.classList.toggle("rg", v === "risinggods");
}
/* Friendly login errors: full detail -> console, shorthand -> UI. */
function shortError(err) {
  const s = String((err && err.message) || err || "");
  console.error("[ygg]", s);
  const t = s.toLowerCase();
  if (t.includes("banned")) return "Account banned.";
  if (t.includes("suspended")) return "Account suspended.";
  if (t.includes("already_online") || t.includes("already online") ||
      t.includes("already in world"))
    return "Account is already online.";
  if (t.includes("locked") || t.includes("lock mismatch"))
    return "Login blocked (IP/country lock).";
  // Proof-stage failure = credentials rejected. NOTE: this server answers
  // WOW_FAIL_UNKNOWN_ACCOUNT even for a wrong password (no account
  // enumeration), so this must come before the unknown-account check.
  // A challenge-stage "no such account" still means an unknown name.
  if (t.includes("proof failed") || t.includes("incorrect_password") ||
      t.includes("incorrect password") || t.includes("wrong account"))
    return "Wrong account name or password.";
  if (t.includes("unknown_account") || t.includes("unknown account") ||
      t.includes("no such account"))
    return "Unknown account name.";
  if (t.includes("version") || t.includes("build rejected"))
    return "Client version rejected by server.";
  if (t.includes("timed out") || t.includes("timeout") ||
      t.includes("stopped responding"))
    return "Connection timed out.";
  if (t.includes("closed the connection") || t.includes("connection closed") ||
      t.includes("refused") || t.includes("unreachable") ||
      t.includes("could not resolve") || t.includes("no such host") ||
      t.includes("failed to fetch") || t.includes("networkerror") ||
      t.includes("load failed"))
    return "Could not reach the server.";
  if (t.includes("db_busy") || t.includes("db busy"))
    return "Server database busy — try again.";
  if (t.includes("no characters")) return "No characters on this realm.";
  if (t.includes("no realms")) return "Server returned no realms.";
  if (t.includes("authenticate first") || t.includes("select a realm") ||
      t.includes("realm first"))
    return "Log in first.";
  if (t.includes("not online") || t.includes("enter the world"))
    return "Enter the world first.";
  if (t.includes("server proof mismatch") || t.includes("srp math"))
    return "Login failed (auth error).";
  if (t.includes("pin") || t.includes("matrix"))
    return "Account needs PIN/matrix entry (unsupported).";
  if (t.includes("authenticator") || t.includes("6-digit"))
    return "Enter your authenticator code and log in again.";
  return "Login failed — try again.";
}
/* Enter in account/password submits, but only when both are filled in */
for (const id of ["username", "password"]) {
  $(id).addEventListener("keydown", (e) => {
    if (e.key === "Enter" && $("username").value.trim() && $("password").value)
      $("btnAuth").click();
  });
}
try {
  const last = localStorage.getItem("ygg_server");
  if (last && (SERVERS[last] || last === "manual")) {
    $("serverPick").value = last;
    $("manualBox").classList.toggle("hidden", last !== "manual");
  }
  const lastUser = localStorage.getItem("ygg_user");
  if (lastUser) { $("username").value = lastUser; $("remember").checked = true; }
} catch { }
syncBranding();
syncTitle();

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) });
  return r.json();
}
function esc(s) {
  return String(s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
/* WoW text formatting: |cAARRGGBB...|r colors, |H..|h[label]|h links. */
function fmt(s) {
  let e = esc(s);
  e = e.replace(/\|T[^|]*\|t/g, "");
  e = e.replace(/\|H[^|]*\|h(.*?)\|h/gi, "$1");
  let open = 0;
  e = e.replace(/\|c([0-9a-fA-F]{8})/g, (m, a) => {
    open++;
    return `<span style="color:#${a.slice(2)}">`;
  });
  e = e.replace(/\|r/g, () => {
    if (open > 0) { open--; return "</span>"; }
    return "";
  });
  while (open-- > 0) e += "</span>";
  return e.replace(/\|/g, "");
}
function busy(btn, on, label) {
  btn.disabled = on;
  if (label !== undefined) btn.dataset.label = btn.textContent, btn.textContent = label;
  else if (btn.dataset.label) btn.textContent = btn.dataset.label, delete btn.dataset.label;
}

/* ---------- wizard ---------- */
function gotoStep(n) {
  for (const i of [1, 2, 3])
    $("pane" + i).classList.toggle("hidden", i !== n);
}
function showLogin() {
  document.body.classList.remove("inchat");
  $("chatView").classList.add("hidden");
  $("loginView").classList.remove("hidden");
  gotoStep(1);
  checkUpdate();
}
function showChat() {
  // Fresh feed every login: never replay a previous session's lines.
  sinceId = 0; feed.innerHTML = "";
  tabs = [{ name: "General", sources: null }]; activeTab = "General";
  lastWho = null; lastChan = null;
  $("kind").value = "say";
  syncTargetBox();
  $("whoResults").innerHTML = "";
  $("whoResults").classList.add("hidden");
  $("chanMembers").innerHTML = "";
  $("chanMembers").classList.add("hidden");
  renderTabs();
  $("loginView").classList.add("hidden");
  $("chatView").classList.remove("hidden");
  document.body.classList.add("inchat");
  $("chatView").classList.remove("menu-collapsed");
  $("gameMenu").classList.remove("open");
}
/* Click a player name anywhere to whisper them. */
function whisperTo(name) {
  name = (name || "").trim();
  if (!name || name.startsWith("guid:")) return;
  $("kind").value = "whisper";
  syncTargetBox();
  $("target").value = name;
  $("whoModal").classList.add("hidden");
  $("chanModal").classList.add("hidden");
  $("text").focus();
}
document.addEventListener("click", (e) => {
  const el = e.target.closest ? e.target.closest("[data-whisper]") : null;
  if (el && el.dataset.whisper) whisperTo(el.dataset.whisper);
});
document.querySelectorAll(".modalx").forEach((b) => {
  b.onclick = () => $(b.dataset.close).classList.add("hidden");
});
/* Update banner on the login page: shown only when a newer build is
   pending on the releases page, otherwise stays hidden (and silent —
   including offline or dev builds with no baked-in version).
   Compares against the tag's live commit (git ref), NOT the release's
   target_commitish field — GitHub freezes that at the branch name given
   at creation ("main"), so it can never match a SHA. */
async function checkUpdate() {
  const box = $("updateBox");
  box.classList.add("hidden");
  try {
    const v = await (await fetch("/api/version")).json();
    const mine = String(v.sha || "");
    if (!mine || mine === "dev") return;
    const ref = await (await fetch(
      `https://api.github.com/repos/${v.repo}/git/refs/tags/${v.tag}`
    )).json();
    const latest = String((ref.object && ref.object.sha) || "");
    if (!latest || ref.message) return;
    if (latest.startsWith(mine) || mine.startsWith(latest)) return;
    const rel = await (await fetch(
      `https://api.github.com/repos/${v.repo}/releases/tags/${v.tag}`
    )).json();
    const link = $("updateLink");
    link.href = v.releases_url;
    const m = /#(\d+)/.exec((rel && rel.name) || "");
    link.textContent =
      m ? `Update available (build #${m[1]})` : "Update available";
    box.classList.remove("hidden");
  } catch { /* offline or unreachable: show nothing */ }
}

$("btnAuth").onclick = async () => {
  const btn = $("btnAuth"), msg = $("authMsg");
  msg.textContent = "";
  const srv = selectedServer();
  if (!srv.host) { msg.textContent = "Enter an auth address."; return; }
  const user = $("username").value.trim();
  if (!user) { msg.textContent = "Enter your account name."; return; }
  busy(btn, true, "Connecting…");
  try {
    const r = await api("/api/auth", {
      auth_host: srv.host,
      auth_port: srv.port,
      username: user,
      password: $("password").value,
      token: $("token").value.trim(),
    });
    $("password").value = "";
    try {
      localStorage.setItem("ygg_server", $("serverPick").value);
      if ($("remember").checked) localStorage.setItem("ygg_user", user);
      else localStorage.removeItem("ygg_user");
    } catch { }
    if (r.need_token) {
      $("tokenBox").classList.remove("hidden");
      msg.textContent = shortError(r.error || "authenticator");
      return;
    }
    if (!r.ok) { msg.textContent = shortError(r.error); return; }
    renderRealms(r.realms);
    gotoStep(2);
  } catch (e) { msg.textContent = shortError(e); }
  finally { busy(btn, false); }
};

/* display maps from /api/meta (single source of truth backend-side) */
let META = { zones: {}, class_colors: {},
  realm_types: { 0: "Normal", 1: "PvP", 4: "Normal", 6: "RP", 8: "RPPvP" } };
let lastRealms = [], lastChars = [];
fetch("/api/meta").then((r) => r.json()).then((m) => {
  META = m;
  // Lists may have rendered before META arrived; repaint if visible
  // (renderers keep the current selection).
  if (lastRealms.length && !$("pane2").classList.contains("hidden"))
    renderRealms(lastRealms);
  if (lastChars.length && !$("pane3").classList.contains("hidden"))
    renderChars(lastChars);
}).catch(() => { });

/* realm list mirrors the in-game table (name/type/chars/population) */
const popName = (p) => p < 0.5 ? "Low" : p < 1 ? "Medium" : p < 2 ? "High" : "Full";

function renderRealms(realms) {
  lastRealms = realms;
  const box = $("realmList");
  box.innerHTML = "";
  if (!realms.some((r) => r.id === pickedRealm))
    pickedRealm = realms.length ? realms[0].id : 0;
  for (const r of realms) {
    const el = document.createElement("div");
    el.className = "realmrow" + (r.id === pickedRealm ? " sel" : "");
    el.innerHTML = `<span class="rname">${esc(r.name)}</span>` +
      `<span>${esc(META.realm_types[r.rtype] || "Normal")}</span>` +
      `<span>(${(r.chars === undefined ? "–" : r.chars)})</span>` +
      `<span>${esc(popName(r.population || 0))}</span>`;
    el.onclick = () => {
      pickedRealm = r.id;
      box.querySelectorAll(".realmrow").forEach((p) => p.classList.remove("sel"));
      el.classList.add("sel");
    };
    el.ondblclick = () => { pickedRealm = r.id; $("btnChars").click(); };
    box.appendChild(el);
  }
  if (!realms.length) box.innerHTML = `<div class="muted">No realms returned.</div>`;
}

$("btnBack1").onclick = () => gotoStep(1);
$("btnChars").onclick = async () => {
  const btn = $("btnChars"), msg = $("realmMsg");
  msg.textContent = "";
  busy(btn, true, "Loading…");
  try {
    const r = await api("/api/characters", { realm_id: pickedRealm });
    if (!r.ok) { msg.textContent = shortError(r.error); return; }
    $("charRealm").textContent = r.realm || "";
    renderChars(r.characters);
    gotoStep(3);
  } catch (e) { msg.textContent = shortError(e); }
  finally { busy(btn, false); }
};

function renderChars(chars) {
  lastChars = chars;
  const box = $("charList");
  box.innerHTML = "";
  if (!chars.some((c) => c.name === pickedChar))
    pickedChar = chars.length ? chars[0].name : "";
  for (const c of chars) {
    const el = document.createElement("div");
    el.className = "charrow" + (c.name === pickedChar ? " sel" : "");
    const icons = (typeof raceSVG === "function" ? raceSVG(c.race, c.gender) : "") +
      (typeof classSVG === "function" ? classSVG(c.class) : "");
    const cc = META.class_colors[c.class] || "#ffd100";
    const zone = META.zones[c.zone] || "";
    el.innerHTML = `<span class="cinfo"><div class="cname">${esc(c.name)}</div>` +
      `<div class="csub">Level ${c.level} <span style="color:${cc}">${esc(CLASSES[c.class] || ("class " + c.class))}</span></div>` +
      (zone ? `<div class="czone">${esc(zone)}</div>` : "") +
      `</span><span class="spr">${icons}</span>`;
    el.onclick = () => {
      pickedChar = c.name;
      box.querySelectorAll(".charrow").forEach((p) => p.classList.remove("sel"));
      el.classList.add("sel");
    };
    el.ondblclick = () => { pickedChar = c.name; $("btnEnter").click(); };
    box.appendChild(el);
  }
  if (!chars.length) box.innerHTML = `<div class="muted">No characters on this realm.</div>`;
}

$("btnBack2").onclick = () => gotoStep(2);
$("btnEnter").onclick = async () => {
  const btn = $("btnEnter"), msg = $("charMsg");
  msg.textContent = "";
  busy(btn, true, "Entering…");
  try {
    const r = await api("/api/enter", { character_name: pickedChar });
    if (!r.ok) { msg.textContent = shortError(r.error); return; }
    currentRace = r.race || 0;
    currentLangs = r.languages || [];
    currentLang = "auto";
    $("btnLangOpen").textContent = "Language: Auto";
    showChat();
    refreshStatus();
  } catch (e) { msg.textContent = shortError(e); }
  finally { busy(btn, false); }
};

/* ---------- chat ---------- */
/* Timestamp display: None | 12h/24h variants. Persisted, applied to
   every feed line (dataset.ts holds the raw epoch seconds). */
let tsFormat = "HHMMSS";
try { tsFormat = localStorage.getItem("ygg_ts") || "HHMMSS"; } catch { }
function fmtTime(tsSec) {
  if (tsFormat === "none") return "";
  const d = new Date((tsSec || 0) * 1000);
  const p2 = (n) => String(n).padStart(2, "0");
  const h24 = d.getHours(), m = p2(d.getMinutes()), s = p2(d.getSeconds());
  const ampm = h24 >= 12 ? "PM" : "AM";
  let h12 = h24 % 12; if (h12 === 0) h12 = 12;
  const H12 = p2(h12);
  if (tsFormat === "hhmm") return `${H12}:${m}`;
  if (tsFormat === "hhmmss") return `${H12}:${m}:${s}`;
  if (tsFormat === "hhmm_ampm") return `${H12}:${m} ${ampm}`;
  if (tsFormat === "hhmmss_ampm") return `${H12}:${m}:${s} ${ampm}`;
  if (tsFormat === "HHMM") return `${p2(h24)}:${m}`;
  return `${p2(h24)}:${m}:${s}`;
}
function refreshTimestamps() {
  feed.querySelectorAll(".line").forEach((div) => {
    const t = div.querySelector(".time");
    if (!t) return;
    const s = fmtTime(parseFloat(div.dataset.ts || "0"));
    t.textContent = s;
    t.style.display = s ? "" : "none";
  });
}
/* Tab sources: 1:1 parity with the in-game General Config (WotLK).
   ids pin to wow/chat_defs.py ChatMsg values (wire uint32); kinds pin to
   CHAT_TYPE_NAMES. Combat/misc opcodes collapse to kind "system" on the
   wire parse, so filtering uses ctype first, kind second. */
const TAB_SOURCES = [
  // Chat — Player Messages
  { id: "say", label: "Say", cat: "chat", ctypes: [0x01] },
  { id: "emote", label: "Emote", cat: "chat", ctypes: [0x0A, 0x0B] },
  { id: "yell", label: "Yell", cat: "chat", ctypes: [0x06] },
  { id: "guild", label: "Guild Chat", cat: "chat", ctypes: [0x04] },
  { id: "officer", label: "Officer Chat", cat: "chat", ctypes: [0x05] },
  { id: "guild_announce", label: "Guild Announce", cat: "chat", ctypes: [0x31] },
  { id: "achievement", label: "Achievement Announce", cat: "chat", ctypes: [0x30] },
  { id: "whisper", label: "Whisper", cat: "chat", ctypes: [0x07, 0x08, 0x09] },
  { id: "real_whisper", label: "Real ID Whisper", cat: "chat", ctypes: [0x2F] },
  { id: "party", label: "Party", cat: "chat", ctypes: [0x02] },
  { id: "party_leader", label: "Party Leader", cat: "chat", ctypes: [0x33] },
  { id: "raid", label: "Raid", cat: "chat", ctypes: [0x03] },
  { id: "raid_leader", label: "Raid Leader", cat: "chat", ctypes: [0x27] },
  { id: "raid_warning", label: "Raid Warning", cat: "chat", ctypes: [0x28] },
  { id: "battleground", label: "Battleground", cat: "chat", ctypes: [0x2C] },
  { id: "bg_leader", label: "Battleground Leader", cat: "chat", ctypes: [0x2D] },
  { id: "real_conv", label: "Real ID Conversation", cat: "chat", ctypes: [0x2F], kinds: ["battlenet"] },
  // Other — Combat
  { id: "xp", label: "Experience", cat: "other", group: "Combat", ctypes: [0x21] },
  { id: "honor", label: "Honor", cat: "other", group: "Combat", ctypes: [0x22] },
  { id: "reputation", label: "Reputation", cat: "other", group: "Combat", ctypes: [0x23] },
  { id: "skill", label: "Skill-ups", cat: "other", group: "Combat", ctypes: [0x1A] },
  { id: "loot", label: "Item Loot", cat: "other", group: "Combat", ctypes: [0x1B] },
  { id: "money", label: "Money Loot", cat: "other", group: "Combat", ctypes: [0x1C] },
  { id: "tradeskills", label: "Tradeskills", cat: "other", group: "Combat", ctypes: [0x1E] },
  { id: "opening", label: "Opening", cat: "other", group: "Combat", ctypes: [0x1D] },
  { id: "pet_info", label: "Pet Info", cat: "other", group: "Combat", ctypes: [0x1F] },
  { id: "misc_info", label: "Misc Info", cat: "other", group: "Combat", ctypes: [0x20] },
  // Other — PvP
  { id: "bg_horde", label: "Battleground Horde", cat: "other", group: "PvP", ctypes: [0x26] },
  { id: "bg_alliance", label: "Battleground Alliance", cat: "other", group: "PvP", ctypes: [0x25] },
  { id: "bg_neutral", label: "Battleground Neutral", cat: "other", group: "PvP", ctypes: [0x24] },
  // Other — Other
  { id: "system", label: "System Messages", cat: "other", group: "Other", ctypes: [0x00] },
  { id: "errors", label: "Errors", cat: "other", group: "Other", ctypes: [-1] },
  { id: "ignored", label: "Ignored", cat: "other", group: "Other", ctypes: [0x19] },
  { id: "chan_notice", label: "Channel", cat: "other", group: "Other", kinds: ["notice"] },
  { id: "target_icons", label: "Target Icons", cat: "other", group: "Other", kinds: ["notice"] },
  { id: "bnet", label: "Battle.net Alerts", cat: "other", group: "Other", ctypes: [0x2F] },
  { id: "afk", label: "AFK", cat: "other", group: "Other", ctypes: [0x17] },
  { id: "dnd", label: "DND", cat: "other", group: "Other", ctypes: [0x18] },
  // Other — Creature Messages
  { id: "m_say", label: "Say", cat: "other", group: "Creature Messages", ctypes: [0x0C] },
  { id: "m_emote", label: "Emote", cat: "other", group: "Creature Messages", ctypes: [0x10] },
  { id: "m_yell", label: "Yell", cat: "other", group: "Creature Messages", ctypes: [0x0E] },
  { id: "m_whisper", label: "Whisper", cat: "other", group: "Creature Messages", ctypes: [0x0F] },
  { id: "m_party", label: "Party", cat: "other", group: "Creature Messages", ctypes: [0x0D] },
  { id: "boss_emote", label: "Boss Emote", cat: "other", group: "Creature Messages", ctypes: [0x29] },
  { id: "boss_whisper", label: "Boss Whisper", cat: "other", group: "Creature Messages", ctypes: [0x2A] },
];
const SOURCE_BY_ID = Object.fromEntries(TAB_SOURCES.map((s) => [s.id, s]));
function sourceMatches(srcId, d) {
  if (srcId.startsWith("chan:")) {
    const want = srcId.slice(5).toLowerCase();
    return (d.channel || "").toLowerCase() === want &&
      (d.kind === "channel" || d.kind === "notice");
  }
  const src = SOURCE_BY_ID[srcId];
  if (!src) return false;
  if (src.ctypes && src.ctypes.includes(d.ctype)) return true;
  if (src.kinds && src.kinds.includes(d.kind)) {
    // kind-only sources (channel notices): ctype agnostic
    if (!src.ctypes) return true;
    // battlenet double-mapped (Real ID Whisper + Conversation share 0x2F)
    if (srcId === "real_conv" && d.ctype === 0x2F) return true;
  }
  return false;
}
/* tabs group the feed; "General" (sources null) shows everything. Tabs are
   only ever created by hand in the tab modal — never automatically. */
let tabs = [{ name: "General", sources: null }], activeTab = "General";
const tabByName = (name) => tabs.find((t) => t.name === name);
function tabMatches(tab, d) {
  if (!tab) return true;
  if (tab.sources != null) return tab.sources.some((s) => sourceMatches(s, d));
  // Backward compat: pre-rebuild tabs stored {channels: [...]}.
  if (tab.channels) {
    const conv = tab.channels.map((c) => c === "__whisper" ? "whisper" : `chan:${String(c).toLowerCase()}`);
    return conv.some((s) => sourceMatches(s, d));
  }
  return true;
}
/* In-game line format: [time] [prefix] sender: text — no badge chips.
   Colors come from .line.<kind> CSS, matching the default client. */
function lineEl(m) {
  const div = document.createElement("div");
  const kind = m.kind || "system";
  div.className = "line " + kind;
  div.dataset.kind = kind;
  div.dataset.channel = m.channel || "";
  const ct = (m.ctype === undefined || m.ctype === null) ? 0 : Number(m.ctype);
  div.dataset.ctype = String(Number.isNaN(ct) ? 0 : ct);
  div.dataset.ts = String(m.ts || 0);
  const ts = fmtTime(m.ts || 0);
  const timeHtml = ts ? `<span class="time">${esc(ts)}</span>` : `<span class="time" style="display:none"></span>`;
  const txt = fmt(m.text || "");
  const sender = m.sender ? esc(m.sender) : "";
  const senderRaw = m.sender || "";
  const toRaw = m.to || "";
  const wattr = (n) => n ? ` data-whisper="${esc(n)}"` : "";
  const ch = m.channel ? esc(m.channel) : "";
  const snd = (name, raw) => name
    ? `<span class="sender clickable"${wattr(raw)}>[${name}]:</span> ` : "";
  const sndBare = (name, raw) => name
    ? `<span class="sender clickable"${wattr(raw)}>[${name}]</span> ` : "";
  let body = "";
  const ctype = Number(div.dataset.ctype);
  if (kind === "notice") {
    body = `${ch ? `<span class="chan">[${ch}]</span> ` : ""}<span class="txt">${txt}</span>`;
  } else if (kind === "system") {
    body = `<span class="txt">${txt}</span>`;
  } else if (kind === "channel") {
    body = `<span class="prefix">[${ch}]</span> ` +
      snd(sender, senderRaw) +
      `<span class="txt">${txt}</span>`;
  } else if (kind === "whisper") {
    body = m.to
      ? `<span class="prefix">To</span> <span class="sender clickable"${wattr(toRaw)}>[${esc(m.to)}]:</span> <span class="txt">${txt}</span>`
      : (sender ? `${sndBare(sender, senderRaw)}<span class="prefix">whispers:</span> <span class="txt">${txt}</span>`
               : `<span class="txt">${txt}</span>`);
  } else if (kind === "guild") {
    body = `<span class="prefix">[Guild]</span> ` +
      snd(sender, senderRaw) + `<span class="txt">${txt}</span>`;
  } else if (kind === "officer") {
    body = `<span class="prefix">[Officer]</span> ` +
      snd(sender, senderRaw) + `<span class="txt">${txt}</span>`;
  } else if (kind === "party") {
    const pl = ctype === 0x33 ? "Party Leader" : "Party";
    body = `<span class="prefix">[${pl}]</span> ` +
      snd(sender, senderRaw) + `<span class="txt">${txt}</span>`;
  } else if (kind === "raid") {
    const pl = ctype === 0x27 ? "Raid Leader" : "Raid";
    body = `<span class="prefix">[${pl}]</span> ` +
      snd(sender, senderRaw) + `<span class="txt">${txt}</span>`;
  } else if (kind === "raid_warning") {
    body = `<span class="prefix">[Raid Warning]</span> <span class="txt">${txt}</span>`;
  } else if (kind === "bg") {
    body = `<span class="prefix">[Battleground]</span> ` +
      snd(sender, senderRaw) + `<span class="txt">${txt}</span>`;
  } else if (kind === "say") {
    body = (sender ? `${sndBare(sender, senderRaw)}<span class="prefix">says:</span> ` : "") +
      `<span class="txt">${txt}</span>`;
  } else if (kind === "yell") {
    body = (sender ? `${sndBare(sender, senderRaw)}<span class="prefix">yells:</span> ` : "") +
      `<span class="txt">${txt}</span>`;
  } else if (kind === "emote") {
    body = (sender ? sndBare(sender, senderRaw) : "") + `<span class="txt">${txt}</span>`;
  } else if (kind === "achievement") {
    body = (sender ? sndBare(sender, senderRaw) : "") + `<span class="txt">${txt}</span>`;
  } else if (kind === "battlenet") {
    body = (sender ? `${sndBare(sender, senderRaw)}<span class="prefix">whispers:</span> ` : "") +
      `<span class="txt">${txt}</span>`;
  } else if (kind === "boss_emote" || kind === "boss_whisper" ||
             kind.startsWith("monster_")) {
    const verb = kind.endsWith("whisper") ? "whispers:" : kind.endsWith("yell") ? "yells:" :
      kind.endsWith("emote") ? "" : "says:";
    body = (sender ? `${sndBare(sender, senderRaw)}` + (verb ? `<span class="prefix">${verb}</span> ` : "") : "") +
      `<span class="txt">${txt}</span>`;
  } else if (kind === "afk" || kind === "dnd") {
    body = `<span class="prefix">[${sender || kind.toUpperCase()}]</span> <span class="txt">${txt}</span>`;
  } else {
    const who = sender ? `<span class="sender clickable"${wattr(senderRaw)}>${sender}</span> ` : "";
    const to = m.to ? `<span class="to clickable"${wattr(toRaw)}>→ ${esc(m.to)}</span> ` : "";
    body = `${who}${to}<span class="txt">${txt}</span>`;
  }
  div.innerHTML = `${timeHtml}${body}`;
  applyTabFilter(div);
  return div;
}
/* tabs filter the feed by their source set; "General" shows everything */
function applyTabFilter(div) {
  const tab = tabByName(activeTab) || tabByName("General");
  if (!tab) { div.style.display = ""; return; }
  const d = {
    kind: div.dataset.kind || "system",
    channel: div.dataset.channel || "",
    ctype: Number(div.dataset.ctype || "0"),
  };
  div.style.display = tabMatches(tab, d) ? "" : "none";
}
function renderTabs() {
  const box = $("tabs");
  box.innerHTML = "";
  for (const t of tabs) {
    const el = document.createElement("button");
    el.className = "tab" + (t.name === activeTab ? " sel" : "");
    el.textContent = t.name;
    const srcs = t.sources || (t.channels ? t.channels : null);
    el.title = srcs ? srcs.join(", ") : "Everything";
    el.onclick = () => { activeTab = t.name; renderTabs(); filterFeed(); };
    if (t.name !== "General") {
      const x = document.createElement("span");
      x.className = "tabx";
      x.textContent = "×";
      x.title = "Close tab";
      x.onclick = (e) => {
        e.stopPropagation();
        tabs = tabs.filter((q) => q !== t);
        if (activeTab === t.name) activeTab = "General";
        renderTabs(); filterFeed();
      };
      el.appendChild(x);
    }
    box.appendChild(el);
  }
}
function filterFeed() {
  feed.querySelectorAll(".line").forEach(applyTabFilter);
}
/* General-Config-style tab modal: Categories left (Chat / Global Channels
   / Other), checkbox list right. Selection is kept while switching
   categories; Global Channels lists joined + custom channels. */
let tabCat = "chat", tabSelected = new Set(), tabCustomChans = [];
function joinedChanNames() {
  const fromSel = [...$("chanJoined").options].map((o) => o.value).filter(Boolean);
  const out = [...fromSel];
  for (const c of tabCustomChans) if (!out.includes(c)) out.push(c);
  return out;
}
function renderTabModal() {
  $("tabName").value = "";
  $("tabMsg").textContent = "";
  tabSelected = new Set();
  tabCustomChans = [];
  tabCat = "chat";
  paintTabModal();
}
function paintTabModal() {
  for (const [id, cat] of [["tabCatChat", "chat"], ["tabCatGlobal", "global"], ["tabCatOther", "other"]])
    $(id).classList.toggle("sel", tabCat === cat);
  const box = $("tabChannels");
  box.innerHTML = "";
  const mk = (value, label) => {
    const lab = document.createElement("label");
    lab.className = "wowcheck left";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = value;
    cb.checked = tabSelected.has(value);
    cb.onchange = () => {
      if (cb.checked) tabSelected.add(value);
      else tabSelected.delete(value);
    };
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(" " + label));
    box.appendChild(lab);
  };
  const mkHead = (label) => {
    const h = document.createElement("div");
    h.className = "whohead";
    h.textContent = label;
    box.appendChild(h);
  };
  if (tabCat === "chat") {
    mkHead("Player Messages");
    for (const s of TAB_SOURCES.filter((s) => s.cat === "chat")) mk(s.id, s.label);
  } else if (tabCat === "global") {
    mkHead("Channels");
    const chans = joinedChanNames();
    if (!chans.length) {
      const d = document.createElement("div");
      d.className = "muted";
      d.textContent = "No channels joined yet — type one below.";
      box.appendChild(d);
    }
    for (const c of chans) mk("chan:" + c.toLowerCase(), c);
  } else {
    let lastGroup = "";
    for (const s of TAB_SOURCES.filter((s) => s.cat === "other")) {
      if (s.group !== lastGroup) { mkHead(s.group); lastGroup = s.group; }
      mk(s.id, s.label);
    }
  }
}
$("btnAddTab").onclick = () => {
  renderTabModal();
  $("tabModal").classList.remove("hidden");
};
$("btnTabClose").onclick = () => $("tabModal").classList.add("hidden");
$("tabModal").addEventListener("click", (e) => {
  if (e.target.id === "tabModal") $("tabModal").classList.add("hidden");
});
$("btnTabCreate").onclick = () => {
  const checked = [...tabSelected];
  const msg = $("tabMsg");
  if (!checked.length) { msg.textContent = "Tick at least one box."; return; }
  let name = $("tabName").value.trim();
  if (!name) {
    const labels = checked.map((v) => v.startsWith("chan:")
      ? v.slice(5) : ((SOURCE_BY_ID[v] || {}).label || v));
    name = labels.length === 1 ? labels[0] : labels.slice(0, 3).join(" + ");
  }
  if (!tabByName(name)) tabs.push({ name, sources: checked });
  activeTab = name;
  $("tabModal").classList.add("hidden");
  renderTabs(); filterFeed();
};
function note(text, kind) {
  feed.appendChild(lineEl({ ts: Date.now() / 1000, kind: kind || "system", ctype: 0, text }));
  feed.scrollTop = feed.scrollHeight;
}
try {
  $("tsFormat").value = tsFormat;
} catch { }
$("tsFormat").addEventListener("change", () => {
  tsFormat = $("tsFormat").value;
  try { localStorage.setItem("ygg_ts", tsFormat); } catch { }
  refreshTimestamps();
});
for (const [id, cat] of [["tabCatChat", "chat"], ["tabCatGlobal", "global"], ["tabCatOther", "other"]])
  $(id).onclick = () => { tabCat = cat; paintTabModal(); };
$("btnTabAddChan").onclick = () => {
  const v = $("tabCustomChan").value.trim();
  if (!v) return;
  if (!tabCustomChans.includes(v)) tabCustomChans.push(v);
  tabSelected.add("chan:" + v.toLowerCase());
  $("tabCustomChan").value = "";
  if (tabCat !== "global") tabCat = "global";
  paintTabModal();
};
async function refreshStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    const was = online;
    online = s.state === "online";
    if (was && !online && !$("chatView").classList.contains("hidden")) {
      // Backend went away (restart/crash) — the WoW session died with it.
      online = false; sinceId = 0; feed.innerHTML = "";
      showLogin(); gotoStep(1);
      $("authMsg").textContent =
        "Backend connection lost — please log in again.";
      console.error("[ygg] backend unreachable or restarted; session lost");
    }
    // Backend lost mid-wizard (e.g. server booted an idle connection):
    // don't leave the user stranded on realm/character select.
    if (s.state === "offline" &&
        !$("loginView").classList.contains("hidden") &&
        (!$("pane2").classList.contains("hidden") ||
         !$("pane3").classList.contains("hidden"))) {
      gotoStep(1);
      $("authMsg").textContent =
        "Connection to the server was lost — please reconnect.";
    }
    if (online) {
      $("whoChar").textContent = s.character || "–";
      $("whoRealm").textContent = s.realm || "";
      if (s.channels) syncChannelLists(s.channels);
      if (s.race && s.race !== currentRace) {
        currentRace = s.race;
        currentLangs = s.languages || currentLangs;
      }
    }
    // Debug stream -> browser console (DevTools, F12). Only new lines.
    if (s.debug) {
      for (const d of s.debug) {
        if (d.ts > lastDebugTs) {
          lastDebugTs = d.ts;
          const t = new Date(d.ts * 1000).toLocaleTimeString();
          console.log(`[ygg ${t}] ${d.msg}`);
        }
      }
    }
  } catch { /* backend starting */ }
}
async function poll() {
  if (!online) return;
  try {
    const d = await (await fetch(`/api/messages?since_id=${sinceId}`)).json();
    for (const m of d.messages || []) {
      sinceId = Math.max(sinceId, m.id);
      if (m.kind === "roster") continue; // answers live in the modals now
      feed.appendChild(lineEl(m));
    }
    if ((d.messages || []).length) feed.scrollTop = feed.scrollHeight;
  } catch { }
}
/* language modal: only the character's racial tongues (+ Auto) */
let currentLang = "auto", currentRace = 0, currentLangs = [];
const LANG_FALLBACK = { 1: "Orcish", 2: "Darnassian", 3: "Taurahe", 6: "Dwarvish",
  7: "Common", 10: "Thalassian", 13: "Gnomish", 14: "Troll", 33: "Gutterspeak", 35: "Draenei" };
function langName(id) {
  return (META.language_names && META.language_names[id]) || LANG_FALLBACK[id] || ("lang " + id);
}
function renderLangModal() {
  const box = $("langList");
  box.innerHTML = "";
  const mk = (value, label) => {
    const b = document.createElement("button");
    b.className = "wowbtn-red";
    b.textContent = label;
    b.onclick = () => {
      currentLang = value;
      $("btnLangOpen").textContent = "Language: " + label;
      $("langModal").classList.add("hidden");
    };
    box.appendChild(b);
  };
  mk("auto", "Auto");
  for (const id of currentLangs) mk(id, langName(id));
}
$("btnLangOpen").onclick = () => { renderLangModal(); $("langModal").classList.remove("hidden"); };
$("btnLangClose").onclick = () => $("langModal").classList.add("hidden");
$("langModal").addEventListener("click", (e) => {
  if (e.target.id === "langModal") $("langModal").classList.add("hidden");
});
/* channel/whisper need a target; other kinds don't show the box.
   Channel target is a selector over actually-joined channels. */
function syncTargetBox() {
  const k = $("kind").value;
  $("target").classList.toggle("hidden", k !== "whisper");
  $("targetSel").classList.toggle("hidden", k !== "channel");
  document.querySelector(".composer").classList.toggle("notarget",
    k !== "channel" && k !== "whisper");
}
function syncChannelLists(channels) {
  for (const id of ["targetSel", "chanJoined"]) {
    const el = $(id);
    const keep = el.value;
    el.innerHTML = "";
    for (const c of channels || []) {
      const o = document.createElement("option");
      o.value = c; o.textContent = c;
      el.appendChild(o);
    }
    if ((channels || []).includes(keep)) el.value = keep;
  }
}
$("kind").addEventListener("change", syncTargetBox);
syncTargetBox();
async function send() {
  const text = $("text").value;
  if (!text || !online) return;
  if (text.startsWith("/join ")) {
    const name = text.slice(6).trim();
    if (name) { await api("/api/join", { name }); note(`Joining ${name}…`, "system"); }
    $("text").value = "";
    return;
  }
  const kind = $("kind").value;
  const r = await api("/api/send", {
    kind, text,
    target: kind === "whisper" ? $("target").value.trim() : "",
    channel: kind === "channel" ? $("targetSel").value : "",
    lang: currentLang,
  });
  if (!r.ok) note("send failed: " + r.error, "system");
  $("text").value = "";
}
$("btnSend").onclick = send;
$("text").addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
/* channel modal: fields + join/leave/members live here, not the menu */
$("btnChanOpen").onclick = () => $("chanModal").classList.remove("hidden");
const mqMobile = window.matchMedia("(max-width: 860px)");
function expandMenu() {
  $("chatView").classList.remove("menu-collapsed");
  if (mqMobile.matches) $("gameMenu").classList.add("open");
}
function toggleMenu() {
  const cv = $("chatView"), gm = $("gameMenu");
  if (cv.classList.contains("menu-collapsed")) { expandMenu(); return; }
  // Mobile keeps its dropdown: title-only -> open -> fully hidden.
  if (mqMobile.matches) {
    if (gm.classList.contains("open")) {
      gm.classList.remove("open");
      cv.classList.add("menu-collapsed");
    } else gm.classList.add("open");
    return;
  }
  cv.classList.add("menu-collapsed");
}
$("btnMenuToggle").onclick = toggleMenu;
$("btnMenuTab").onclick = expandMenu;
$("btnChanClose").onclick = () => $("chanModal").classList.add("hidden");
$("chanModal").addEventListener("click", (e) => {
  if (e.target.id === "chanModal") $("chanModal").classList.add("hidden");
});
$("btnJoin").onclick = async () => {
  const name = $("chanName").value.trim(); if (!name) return;
  const r = await api("/api/join", { name, password: $("chanPass").value });
  note(r.ok ? `Joining ${name}…` : `join failed: ${r.error}`, "system");
  if (r.ok) $("chanModal").classList.add("hidden");
};
$("btnLeave").onclick = async () => {
  const name = $("chanJoined").value; if (!name) return;
  await api("/api/leave", { name });
  note(`Left ${name}.`, "system");
};
$("btnChanList").onclick = async () => {
  const name = $("chanJoined").value; if (!name) return;
  const btn = $("btnChanList"), msg = $("chanMsg");
  msg.textContent = "";
  busy(btn, true, "Loading…");
  try {
    const r = await api("/api/chanlist", { name });
    if (!r.ok) { msg.textContent = shortError(r.error); return; }
    msg.textContent = "Loading…";
    const before = lastChan ? lastChan.ts : 0;
    const res = await pollResult("/api/chan_result", before);
    if (!res) { msg.textContent = "No answer from server."; return; }
    lastChan = res;
    renderChanResult(res.detail);
    msg.textContent = "";
    // Names resolve in the background — repaint once so guid:123
    // placeholders turn into real names.
    setTimeout(async () => {
      try {
        const fresh = await (await fetch("/api/chan_result")).json();
        if (fresh.present && fresh.ts === lastChan.ts) {
          lastChan = fresh;
          renderChanResult(fresh.detail);
        }
      } catch { }
    }, 2500);
  } catch (e) { msg.textContent = shortError(e); }
  finally { busy(btn, false); }
};
/* latest answer only: who / channel members render into their modal,
   never into the chat feed. Result boxes stay hidden until populated. */
let lastWho = null, lastChan = null;
async function pollResult(url, sinceTs, tries = 12) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await (await fetch(url)).json();
      if (r.present && (r.ts || 0) !== sinceTs) return r;
    } catch { }
    await new Promise((res) => setTimeout(res, 800));
  }
  return null;
}
function renderWhoResult(detail) {
  const box = $("whoResults");
  box.innerHTML = "";
  const entries = (detail && detail.entries) || [];
  if (detail && detail.error) {
    const div = document.createElement("div");
    div.className = "line roster";
    div.innerHTML = `<span class="txt">Error: ${esc(detail.error)}</span>`;
    box.appendChild(div);
  } else if (!entries.length) {
    box.innerHTML = `<div class="muted">No matches.</div>`;
  } else {
    const head = document.createElement("div");
    head.className = "whohead";
    head.textContent = `${detail.count ?? entries.length} shown`;
    box.appendChild(head);
    for (const e of entries.slice(0, 50)) {
      const div = document.createElement("div");
      div.className = "line roster";
      const cc = META.class_colors[e.class] || "#ffd100";
      const zone = META.zones[e.zone] || "";
      div.innerHTML = `<span class="txt"><b class="whoname" data-whisper="${esc(e.name)}">${esc(e.name)}</b> — ` +
        `Level ${e.level} ` +
        `<span style="color:${cc}">${esc(CLASSES[e.class] || ("class " + e.class))}</span> ` +
        `${esc(RACES[e.race] || ("race " + e.race))}` +
        (zone ? ` — ${esc(zone)}` : "") +
        (e.guild ? ` <span class="muted">[${esc(e.guild)}]</span>` : "") +
        `</span>`;
      box.appendChild(div);
    }
  }
  box.classList.remove("hidden");
  box.scrollTop = 0;
}
function renderChanResult(detail) {
  const box = $("chanMembers");
  box.innerHTML = "";
  if (detail && detail.error) {
    box.innerHTML = `<div class="line roster"><span class="txt">` +
      `Error: ${esc(detail.error)}</span></div>`;
  } else {
    const members = (detail && detail.members) || [];
    const head = document.createElement("div");
    head.className = "whohead";
    head.textContent =
      `${detail.channel || ""}: ${detail.count ?? members.length} member(s)`;
    box.appendChild(head);
    if (!members.length) {
      box.innerHTML += `<div class="muted">No members listed.</div>`;
    } else {
      for (const m of members) {
        const div = document.createElement("div");
        div.className = "line roster";
        const nm = m.name || ("guid:" + m.guid);
        div.innerHTML = nm.startsWith("guid:")
          ? `<span class="txt">${esc(nm)}</span>`
          : `<span class="txt"><span class="whoname" data-whisper="${esc(nm)}">${esc(nm)}</span></span>`;
        box.appendChild(div);
      }
    }
  }
  box.classList.remove("hidden");
  box.scrollTop = 0;
}
$("btnWho").onclick = async () => {
  const btn = $("btnWho"), msg = $("whoMsg");
  msg.textContent = "";
  const q = $("whoName").value.trim();
  busy(btn, true, "Searching…");
  try {
    const before = lastWho ? lastWho.ts : 0;
    const r = await api("/api/who", { name_sub: q });
    if (!r.ok) { msg.textContent = shortError(r.error); return; }
    msg.textContent = "Searching…";
    const res = await pollResult("/api/who_result", before);
    if (!res) { msg.textContent = "No answer from server."; return; }
    lastWho = res;
    renderWhoResult(res.detail);
    msg.textContent = "";
  } catch (e) { msg.textContent = shortError(e); }
  finally { busy(btn, false); }
};
$("btnWhoOpen").onclick = () => {
  if (lastWho) renderWhoResult(lastWho.detail);
  $("whoModal").classList.remove("hidden");
};
$("btnWhoClose").onclick = () => $("whoModal").classList.add("hidden");
$("whoModal").addEventListener("click", (e) => {
  if (e.target.id === "whoModal") $("whoModal").classList.add("hidden");
});
/* feed browse buttons */
$("btnUp").onclick = () => feed.scrollBy({ top: -feed.clientHeight * 0.9 });
$("btnDown").onclick = () => feed.scrollBy({ top: feed.clientHeight * 0.9 });
$("btnLogout").onclick = async () => {
  await api("/api/logout");
  online = false; sinceId = 0; feed.innerHTML = "";
  tabs = [{ name: "General", sources: null }]; activeTab = "General";
  lastWho = null; lastChan = null;
  $("whoResults").innerHTML = "";
  $("whoResults").classList.add("hidden");
  $("chanMembers").innerHTML = "";
  $("chanMembers").classList.add("hidden");
  renderTabs();
  showLogin();
  refreshStatus();
};
gotoStep(1);
renderTabs();
checkUpdate();
refreshStatus();
setInterval(refreshStatus, 3000);
pollTimer = setInterval(poll, 1000);
