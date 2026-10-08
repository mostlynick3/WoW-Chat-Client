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
  $("chatView").classList.add("hidden");
  $("loginView").classList.remove("hidden");
  gotoStep(1);
  checkUpdate();
}
function showChat() {
  // Fresh feed every login: never replay a previous session's lines.
  sinceId = 0; feed.innerHTML = "";
  tabs = ["All"]; activeTab = "All";
  lastWho = null; lastChan = null;
  $("whoResults").innerHTML = "";
  $("whoResults").classList.add("hidden");
  $("chanMembers").innerHTML = "";
  $("chanMembers").classList.add("hidden");
  renderTabs();
  $("loginView").classList.add("hidden");
  $("chatView").classList.remove("hidden");
}
/* Update banner on the login page: shown only when a newer build is
   pending on the releases page, otherwise stays hidden (and silent —
   including offline or dev builds with no baked-in version). */
async function checkUpdate() {
  const box = $("updateBox");
  box.classList.add("hidden");
  try {
    const v = await (await fetch("/api/version")).json();
    const mine = String(v.sha || "");
    if (!mine || mine === "dev") return;
    const r = await (await fetch(
      `https://api.github.com/repos/${v.repo}/releases/tags/${v.tag}`
    )).json();
    if (!r || r.message || !r.target_commitish) return;
    const latest = String(r.target_commitish);
    if (latest.startsWith(mine) || mine.startsWith(latest)) return;
    const link = $("updateLink");
    link.href = v.releases_url;
    const m = /#(\d+)/.exec(r.name || "");
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
let tabs = ["All"], activeTab = "All";
function lineEl(m) {
  const div = document.createElement("div");
  div.className = "line " + (m.kind || "system");
  div.dataset.kind = m.kind || "system";
  div.dataset.channel = m.channel || "";
  const t = new Date((m.ts || 0) * 1000).toLocaleTimeString();
  const badge = { say: "SAY", yell: "YELL", whisper: "WISP", channel: "CHAN",
    guild: "GUILD", party: "PARTY", raid: "RAID", echo: "YOU",
    system: "•••", notice: "CHAN", roster: "WHO" }[(m.kind || "system")] || esc(m.kind);
  // Notices: channel badge + short text (sender never repeats it).
  if ((m.kind || "") === "notice") {
    const ch = m.channel ? `<span class="chan">[${esc(m.channel)}]</span> ` : "";
    div.innerHTML = `${ch}<span class="txt">${fmt(m.text || "")}</span>`;
  } else {
    const who = m.sender ? `<span class="who">${esc(m.sender)}</span> ` : "";
    const ch = m.channel ? `<span class="chan">[${esc(m.channel)}]</span> ` : "";
    div.innerHTML = `<span class="time">${t}</span><span class="tag">${badge}</span>` +
      `${who}${ch}<span class="txt">${fmt(m.text || "")}</span>`;
  }
  applyTabFilter(div);
  return div;
}
/* tabs filter the feed by channel; "All" shows everything */
function applyTabFilter(div) {
  const show = activeTab === "All" || (div.dataset.channel || "") === activeTab;
  div.style.display = show ? "" : "none";
}
function renderTabs() {
  const box = $("tabs");
  box.innerHTML = "";
  for (const name of tabs) {
    const el = document.createElement("button");
    el.className = "tab" + (name === activeTab ? " sel" : "");
    el.textContent = name === "All" ? "All" : name;
    el.title = name;
    el.onclick = () => { activeTab = name; renderTabs(); filterFeed(); };
    if (name !== "All") {
      const x = document.createElement("span");
      x.className = "tabx";
      x.textContent = "×";
      x.title = "Close tab";
      x.onclick = (e) => {
        e.stopPropagation();
        tabs = tabs.filter((t) => t !== name);
        if (activeTab === name) activeTab = "All";
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
function ensureTab(channel) {
  if (channel && !tabs.includes(channel)) {
    tabs.push(channel);
    renderTabs();
  }
}
$("btnAddTab").onclick = () => {
  const name = prompt("Tab (channel) name:");
  if (name && name.trim()) {
    ensureTab(name.trim());
    activeTab = name.trim();
    renderTabs(); filterFeed();
  }
};
function note(text, kind) {
  feed.appendChild(lineEl({ ts: Date.now() / 1000, kind: kind || "system", text }));
  feed.scrollTop = feed.scrollHeight;
}
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
      if ((m.kind === "channel" || m.kind === "notice") && m.channel) ensureTab(m.channel);
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
      div.innerHTML = `<span class="txt"><b>${esc(e.name)}</b> — ` +
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
        div.innerHTML = `<span class="txt">${esc(m.name || ("guid:" + m.guid))}</span>`;
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
  tabs = ["All"]; activeTab = "All";
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
