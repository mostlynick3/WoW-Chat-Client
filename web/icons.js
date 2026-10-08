"use strict";
// Real 3.3.5a race/class icons (Blizzard art via wowhead CDN, verified live),
// with the built-in geometric SVGs below as offline fallback.
const ICON_BASE = "https://wow.zamimg.com/images/wow/icons/medium/";
const RACE_ICON = { 1: "race_human", 2: "race_orc", 3: "race_dwarf", 4: "race_nightelf",
  5: "race_scourge", 6: "race_tauren", 7: "race_gnome", 8: "race_troll",
  10: "race_bloodelf", 11: "race_draenei" };
const CLASS_ICON = { 1: "class_warrior", 2: "class_paladin", 3: "class_hunter",
  4: "class_rogue", 5: "class_priest", 6: "class_deathknight", 7: "class_shaman",
  8: "class_mage", 9: "class_warlock", 11: "class_druid" };

function iconImg(name, alt, kind, id) {
  return `<img src="${ICON_BASE}${name}.jpg" alt="${alt}" loading="lazy" ` +
    `onerror="__yggIconFb(this,'${kind}',${id})">`;
}
function raceSVG(race, gender) {
  const base = RACE_ICON[race || 0];
  if (!base) return raceFallback(race);
  const suffix = (gender === 1) ? "_female" : "_male";
  return iconImg(base + suffix, base, "r", race || 0);
}
function classSVG(cls) {
  const base = CLASS_ICON[cls || 0];
  if (!base) return classFallback(cls);
  return iconImg(base, base, "c", cls || 0);
}
// CDN miss/offline -> swap in the geometric fallback.
function __yggIconFb(el, kind, id) {
  el.outerHTML = kind === "r" ? raceFallback(id) : classFallback(id);
}

// ---- offline fallback: simple geometric emblems, faction tinted ----
const RACE_COLOR = { ally: "#4f8ff7", horde: "#e5534b" };
const CLASS_COLOR = { 1: "#c79c6e", 2: "#f58cba", 3: "#abd473", 4: "#fff569",
  5: "#ffffff", 6: "#c41f3b", 7: "#0070de", 8: "#69ccf0", 9: "#9482c9", 11: "#ff7d0a" };

function svgWrap(inner, color) {
  return `<svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">` +
    `<circle cx="16" cy="16" r="15" fill="#0e141b" stroke="${color}" stroke-width="1.6"/>` +
    `<g stroke="${color}" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${inner}</g></svg>`;
}
function head(extras) {
  return `<circle cx="16" cy="17" r="6" fill="FILL"/>${extras || ""}`;
}
const RACE_GLYPH = {
  1: "",
  2: `<path d="M11 21l-1.5 3M21 21l1.5 3"/>`,
  3: `<path d="M11 20h10l-2 6h-6z"/>`,
  4: `<path d="M10 15L3 12l6-1M22 15l7-3-6-1"/>`,
  5: `<path d="M13.5 16h5M13.5 19h5"/>`,
  6: `<path d="M10 12C6 10 5 6 6 3c3 1 5 3 6 6M22 12c4-2 5-6 4-9-3 1-5 3-6 6"/>`,
  7: `<path d="M16 11V4l4 7z"/>`,
  8: `<path d="M16 17l0 5M10 14l-4 2M22 14l4 2"/>`,
  10: `<path d="M10 13l-4-4M22 13l4-4"/>`,
  11: `<path d="M11 11c-2-1-2-4 0-5M21 11c2-1 2-4 0-5M13 23c1 2 5 2 6 0"/>`,
};
const CLASS_GLYPH = {
  1: `<path d="M9 23L23 9M9 23l-2 2M9 23l2-2M23 9l1-3 3 1M9 9l14 14"/>`,
  2: `<path d="M16 6v16M10 12h12"/><circle cx="16" cy="16" r="9" opacity=".45"/>`,
  3: `<path d="M10 6c6 4 6 16 0 20M10 6c-2 7-2 13 0 20M10 16h12M22 16l-3-2M22 16l-3 2"/>`,
  4: `<path d="M11 23L21 9l-2-2L9 21zM19 7l2-2"/>`,
  5: `<circle cx="16" cy="16" r="3"/><path d="M16 5v4M16 23v4M5 16h4M23 16h4M8 8l2 2M24 8l-2 2M8 24l2-2M24 24l-2-2"/>`,
  6: `<circle cx="16" cy="15" r="6"/><circle cx="13.7" cy="14" r="1.2" fill="#0e141b" stroke="none"/><circle cx="18.3" cy="14" r="1.2" fill="#0e141b" stroke="none"/><path d="M13 26h6"/>`,
  7: `<path d="M18 5l-7 10h5l-2 8 8-12h-5z"/>`,
  8: `<path d="M10 26L20 8M20 8l-3-1M20 8l1-3"/><path d="M23 12l1 2 2 1-2 1-1 2-1-2-2-1 2-1z"/>`,
  9: `<path d="M16 25c-4 0-6-2-6-6 0-5 6-4 6-9 3 2 3 4 2 6 2 0 4 2 4 4 0 3-2 5-6 5z"/>`,
  11: `<circle cx="16" cy="17" r="5"/><circle cx="11" cy="11" r="2"/><circle cx="21" cy="11" r="2"/><circle cx="11" cy="23" r="2"/><circle cx="21" cy="23" r="2"/>`,
};
function factionOfRaceIcon(r) {
  return [1, 3, 4, 7, 11].includes(r) ? "ally" : "horde";
}
function raceFallback(race) {
  const c = RACE_COLOR[factionOfRaceIcon(race || 0)] || "#93a3b5";
  const g = RACE_GLYPH[race] !== undefined ? RACE_GLYPH[race] : "";
  return svgWrap(head(g).replace(/FILL/g, c + "22"), c);
}
function classFallback(cls) {
  const c = CLASS_COLOR[cls] || "#93a3b5";
  const g = CLASS_GLYPH[cls] || `<circle cx="16" cy="16" r="5"/>`;
  return svgWrap(g, c);
}
