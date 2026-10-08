"use strict";
let sinceId = 0, online = false, pollTimer = null;

const $ = (id) => document.getElementById(id);
const feed = $("feed"), dot = $("dot"), connText = $("connText");

function lineEl(m) {
  const div = document.createElement("div");
  div.className = "line " + (m.kind || "system");
  const t = new Date((m.ts || 0) * 1000).toLocaleTimeString();
  const who = m.sender ? `<span class="who">${esc(m.sender)}</span> ` : "";
  const ch = m.channel ? `<span class="chan">[${esc(m.channel)}]</span> ` : "";
  div.innerHTML = `<span>[${t}]</span> ${who}${ch}<span class="txt">${esc(m.text || "")}</span>`;
  return div;
}
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function note(text, kind) {
  feed.appendChild(lineEl({ ts: Date.now() / 1000, kind: kind || "system", text }));
  feed.scrollTop = feed.scrollHeight;
}
async function api(path, body) {
  const r = await fetch(path, body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
}
async function refreshStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    online = s.state === "online";
    dot.className = online ? "on" : (s.state === "offline" ? "" : "busy");
    connText.textContent = `${s.state} — ${s.status || ""}`;
    $("chatCard").classList.toggle("hidden", false);
    if (online) $("whoami").textContent = `— ${s.character} @ ${s.realm}`;
  } catch { /* backend starting */ }
}
async function poll() {
  try {
    const d = await (await fetch(`/api/messages?since_id=${sinceId}`)).json();
    for (const m of d.messages || []) {
      sinceId = Math.max(sinceId, m.id);
      feed.appendChild(lineEl(m));
    }
    if ((d.messages || []).length) feed.scrollTop = feed.scrollHeight;
  } catch { }
}

$("btnLogin").onclick = async () => {
  $("loginMsg").textContent = "connecting…";
  const body = {
    auth_host: $("authHost").value.trim() || "127.0.0.1",
    auth_port: +$("authPort").value || 3724,
    username: $("username").value.trim(),
    password: $("password").value,
    realm_id: +$("realmId").value || 1,
    character_name: $("charName").value.trim(),
    world_host_override: $("worldHost").value.trim(),
    world_port_override: +$("worldPort").value || 0,
  };
  $("password").value = "";  // don't keep password in the DOM
  const r = await api("/api/login", body);
  $("loginMsg").textContent = r.ok ? `online as ${r.character}` : `FAILED: ${r.error}`;
  if (r.ok) note(`Logged in as ${r.character}.`, "system");
  refreshStatus();
};
$("btnLogout").onclick = async () => {
  await api("/api/logout");
  note("Logged out.", "system");
  refreshStatus();
};
async function send() {
  let text = $("text").value;
  if (!text) return;
  // slash shortcut: /join ChannelName
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
    channel: kind === "channel" ? ($("target").value.trim() || "World") : "",
    lang: +$("lang").value || 7,
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

refreshStatus();
setInterval(refreshStatus, 3000);
pollTimer = setInterval(poll, 1000);
poll();
