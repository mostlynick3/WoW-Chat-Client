"use strict";
let sinceId = 0, online = false, pollTimer = null, lastDebugTs = 0;
const dbgLines = [];
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
  try { localStorage.setItem("ygg_server", $("serverPick").value); } catch { }
});
try {
  const last = localStorage.getItem("ygg_server");
  if (last && (SERVERS[last] || last === "manual")) {
    $("serverPick").value = last;
    $("manualBox").classList.toggle("hidden", last !== "manual");
  }
  const lastUser = localStorage.getItem("ygg_user");
  if (lastUser) $("username").value = lastUser;
} catch { }

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
function busy(btn, on, label) {
  btn.disabled = on;
  if (label !== undefined) btn.dataset.label = btn.textContent, btn.textContent = label;
  else if (btn.dataset.label) btn.textContent = btn.dataset.label, delete btn.dataset.label;
}

/* ---------- wizard ---------- */
function gotoStep(n) {
  for (const i of [1, 2, 3]) {
    $("pane" + i).classList.toggle("hidden", i !== n);
    const d = $("step" + i + "dot");
    d.classList.toggle("active", i === n);
    d.classList.toggle("done", i < n);
  }
}
function showLogin() {
  $("chatView").classList.add("hidden");
  $("loginView").classList.remove("hidden");
  gotoStep(1);
}
function showChat() {
  $("loginView").classList.add("hidden");
  $("chatView").classList.remove("hidden");
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
    });
    $("password").value = "";
    try {
      localStorage.setItem("ygg_server", $("serverPick").value);
      localStorage.setItem("ygg_user", user);
    } catch { }
    if (!r.ok) { msg.textContent = "Failed: " + r.error; return; }
    renderRealms(r.realms);
    gotoStep(2);
  } catch (e) { msg.textContent = "Failed: " + e; }
  finally { busy(btn, false); }
};

function renderRealms(realms) {
  const box = $("realmList");
  box.innerHTML = "";
  pickedRealm = realms.length ? realms[0].id : 0;
  for (const r of realms) {
    const el = document.createElement("div");
    el.className = "pick" + (r.id === pickedRealm ? " sel" : "");
    el.innerHTML = `<span class="radio"></span><span><div class="main">${esc(r.name)}</div>` +
      `<div class="sub">${esc(r.address)}</div></span>`;
    el.onclick = () => {
      pickedRealm = r.id;
      box.querySelectorAll(".pick").forEach((p) => p.classList.remove("sel"));
      el.classList.add("sel");
    };
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
    if (!r.ok) { msg.textContent = "Failed: " + r.error; return; }
    renderChars(r.characters);
    gotoStep(3);
  } catch (e) { msg.textContent = "Failed: " + e; }
  finally { busy(btn, false); }
};

function renderChars(chars) {
  const box = $("charList");
  box.innerHTML = "";
  pickedChar = chars.length ? chars[0].name : "";
  for (const c of chars) {
    const f = factionOf(c.race || 0);
    const el = document.createElement("div");
    el.className = "pick" + (c.name === pickedChar ? " sel" : "");
    el.innerHTML = `<span class="radio"></span><span><div class="main">${esc(c.name)} ` +
      `<span class="faction-${f[0]}">· ${f}</span></div>` +
      `<div class="sub">Lv ${c.level} ${esc(RACES[c.race] || ("race " + c.race))} ` +
      `${esc(CLASSES[c.class] || ("class " + c.class))}</div></span>` +
      `<span class="lvl">Lv ${c.level}</span>`;
    el.onclick = () => {
      pickedChar = c.name;
      box.querySelectorAll(".pick").forEach((p) => p.classList.remove("sel"));
      el.classList.add("sel");
    };
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
    if (!r.ok) { msg.textContent = "Failed: " + r.error; return; }
    note(`Logged in as ${r.character}${r.faction ? ` (${r.faction})` : ""}.`, "system");
    showChat();
    refreshStatus();
  } catch (e) { msg.textContent = "Failed: " + e; }
  finally { busy(btn, false); }
};

/* ---------- chat ---------- */
function lineEl(m) {
  const div = document.createElement("div");
  div.className = "line " + (m.kind || "system");
  const t = new Date((m.ts || 0) * 1000).toLocaleTimeString();
  const badge = { say: "SAY", yell: "YELL", whisper: "WISP", channel: "CHAN",
    guild: "GUILD", party: "PARTY", raid: "RAID", echo: "YOU",
    system: "•••", notice: "CHAN", roster: "WHO" }[(m.kind || "system")] || esc(m.kind);
  const who = m.sender ? `<span class="who">${esc(m.sender)}</span> ` : "";
  const ch = m.channel ? `<span class="chan">[${esc(m.channel)}]</span> ` : "";
  div.innerHTML = `<span class="time">${t}</span><span class="tag">${badge}</span>` +
    `${who}${ch}<span class="txt">${esc(m.text || "")}</span>`;
  return div;
}
function note(text, kind) {
  feed.appendChild(lineEl({ ts: Date.now() / 1000, kind: kind || "system", text }));
  feed.scrollTop = feed.scrollHeight;
}
async function refreshStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    online = s.state === "online";
    $("dot").className = online ? "on" : (s.state === "offline" ? "" : "busy");
    $("connText").textContent = `${s.state} — ${s.status || ""}`.slice(0, 90);
    if (online) {
      $("whoChar").textContent = s.character || "–";
      $("whoRealm").textContent = s.realm || "";
      const fb = $("factionBadge");
      fb.textContent = s.faction || "–";
      fb.className = "badge " + (s.faction === "alliance" ? "ally" : s.faction === "horde" ? "horde" : "");
      $("uniBadge").textContent = "universal: " + (s.universal || "unknown");
    }
    const dbg = $("debugLog");
    if (dbg && s.debug) {
      let added = false;
      for (const d of s.debug) {
        if (d.ts > lastDebugTs) {
          lastDebugTs = d.ts;
          const t = new Date(d.ts * 1000).toLocaleTimeString();
          dbgLines.push(`[${t}] ${d.msg}`);
          added = true;
        }
      }
      if (added) {
        while (dbgLines.length > 200) dbgLines.shift();
        dbg.textContent = dbgLines.join("\n") + "\n";
        dbg.scrollTop = dbg.scrollHeight;
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
      feed.appendChild(lineEl(m));
    }
    if ((d.messages || []).length) feed.scrollTop = feed.scrollHeight;
  } catch { }
}
async function send() {
  const text = $("text").value;
  if (!text || !online) return;
  if (text.startsWith("/join ")) {
    const name = text.slice(6).trim();
    if (name) { await api("/api/join", { name }); note(`Joining ${name}…`, "system"); }
    $("text").value = "";
    return;
  }
  const kind = $("kind").value, lv = $("lang").value;
  const r = await api("/api/send", {
    kind, text,
    target: kind === "whisper" ? $("target").value.trim() : "",
    channel: kind === "channel" ? ($("target").value.trim() || "World") : "",
    lang: lv === "auto" ? "auto" : +lv,
  });
  if (!r.ok) note("send failed: " + r.error, "system");
  $("text").value = "";
}
$("btnSend").onclick = send;
$("text").addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
$("btnJoin").onclick = async () => {
  const name = $("chanName").value.trim(); if (!name) return;
  const r = await api("/api/join", { name, password: $("chanPass").value });
  note(r.ok ? `Joining ${name}…` : `join failed: ${r.error}`, "system");
};
$("btnLeave").onclick = async () => {
  const name = $("chanName").value.trim(); if (!name) return;
  await api("/api/leave", { name });
  note(`Left ${name}.`, "system");
};
$("btnChanList").onclick = async () => {
  const name = $("chanName").value.trim(); if (!name) return;
  await api("/api/chanlist", { name });
};
$("btnWho").onclick = async () => {
  await api("/api/who", { name_sub: $("whoName").value.trim() });
};
$("btnLogout").onclick = async () => {
  await api("/api/logout");
  online = false; sinceId = 0; feed.innerHTML = "";
  showLogin();
  refreshStatus();
};

gotoStep(1);
refreshStatus();
setInterval(refreshStatus, 3000);
pollTimer = setInterval(poll, 1000);
