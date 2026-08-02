"use strict";
/* c-cleaner 前端 v2 — hash 路由 5 视图 + 全局清理篮
   由 report.py 内联进单文件 report.html；file:// 打开为只读模式，
   经 serve.py 打开(127.0.0.1:8756)解锁清理/AI 功能。 */

const DATA = __DATA__;
const AI_NOTES = __AI_NOTES__;

const S = {
  safe:    { icon: "✅", label: "可放心清理",       color: "var(--safe)",    bg: "var(--safe-bg)",    order: 0 },
  caution: { icon: "⚠️", label: "可清理·注意方法",   color: "var(--caution)", bg: "var(--caution-bg)", order: 1 },
  user:    { icon: "👤", label: "个人文件·自行决定", color: "var(--user)",    bg: "var(--user-bg)",    order: 2 },
  none:    { icon: "❔", label: "未识别",           color: "var(--none)",    bg: "var(--none-bg)",    order: 3 },
  danger:  { icon: "🚫", label: "别手动删",         color: "var(--danger)",  bg: "var(--danger-bg)",  order: 4 },
  keep:    { icon: "🔒", label: "保留勿删",         color: "var(--keep)",    bg: "var(--keep-bg)",    order: 5 },
};
const aiMap = {};
AI_NOTES.notes.forEach(n => aiMap[n.path.toLowerCase()] = n);
const m = DATA.meta;

let SERVER = false, AI_AVAIL = false, AI_PROVIDER = null;
const basket = new Map();          // path -> {path,size,source,title,safety,base,name}
const cleanedMap = {};             // path(lower) -> {bytes}
const detailCache = {}, browseCache = {}, safeScanCache = {};
let dupeData = null, leftData = null;
let filter = "all", sortKey = "size", sortDir = -1;
const expanded = new Set();
let navStack = [];                 // treemap
let expStack = ["C:"];             // browser

/* ---------- utils ---------- */
function fmt(b) {
  if (b >= 1024**3) return (b/1024**3).toFixed(2) + " GB";
  if (b >= 1024**2) return (b/1024**2).toFixed(1) + " MB";
  return (b/1024).toFixed(0) + " KB";
}
function esc(s) { return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;"); }
async function api(ep, body) {
  const r = await fetch(ep, { method: "POST",
    headers: {"Content-Type":"application/json", "X-CC-Token": window.CC_TOKEN || ""},
    body: JSON.stringify(body || {}) });
  return r.json();
}
function el(tag, attrs, html) {
  const e = document.createElement(tag);
  for (const [k,v] of Object.entries(attrs || {})) {
    if (k === "onclick") e.addEventListener("click", v);
    else if (k === "className") e.className = v;
    else e.setAttribute(k, v);
  }
  if (html != null) e.innerHTML = html;
  return e;
}
function toast(msg, bad) {
  const t = el("div", {className: "toast" + (bad ? " bad" : "")}, esc(msg));
  document.getElementById("toasts").appendChild(t);
  setTimeout(() => t.remove(), bad ? 8000 : 4500);
}
function spin(txt) {
  return `<div style="padding:20px;text-align:center"><span class="spin"></span>
    <div class="hint" style="margin-top:8px">${esc(txt)}</div></div>`;
}

/* ---------- 路由 ---------- */
const VIEWS = ["map", "list", "browse", "tools", "quarantine"];
function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [name, qs] = h.split("?");
  const params = new URLSearchParams(qs || "");
  return { view: VIEWS.includes(name) ? name : "map", params };
}
function route() {
  const { view, params } = parseHash();
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("on", v.id === "view-" + view));
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("on", t.dataset.v === view));
  if (view === "map") renderTreemap();
  if (view === "list") renderRows();
  if (view === "browse") {
    const p = params.get("path");
    if (p) {
      const cur = expStack[expStack.length-1];
      if (cur !== p) {
        const i = expStack.indexOf(p);
        if (i >= 0) expStack = expStack.slice(0, i+1);
        else if (p.startsWith(cur + "/")) expStack.push(p);
        else expStack = [p];
      }
    }
    renderBrowse();
  }
  if (view === "tools") renderTools();
  if (view === "quarantine") renderQuarantine();
}
window.addEventListener("hashchange", route);
document.getElementById("tabs").addEventListener("click", e => {
  const t = e.target.closest(".tab");
  if (t) location.hash = "#/" + t.dataset.v;
});
function gotoBrowse(path) {
  location.hash = "#/browse?path=" + encodeURIComponent(path).replace(/%2F/gi, "/");
}

/* ---------- 顶部 ---------- */
{
  let metaTxt = `${m.target} · 扫描于 ${m.scanned_at} · ${m.file_count.toLocaleString()} 个文件 · 耗时 ${m.elapsed_sec} 秒`;
  const pv = DATA.prev_scan;
  if (pv) {
    const df = m.disk_free - pv.disk_free;
    metaTxt += ` · 较上次(${pv.ts.slice(5,16)})剩余空间${df >= 0 ? "+" : "−"}${fmt(Math.abs(df))}`;
  }
  document.getElementById("meta").textContent = metaTxt;
  document.getElementById("capbar").innerHTML = [
    ["used", m.scanned_size], ["hidden-part", m.unscanned_size], ["free", m.disk_free],
  ].map(([cls, v]) => `<div class="${cls}" style="flex:${Math.max(v,1)}" title="${fmt(v)}"></div>`).join("");
  document.getElementById("caplegend").innerHTML =
    `<span>■ 已扫描 <b>${fmt(m.scanned_size)}</b></span>` +
    `<span>▨ 扫描不到 <b>${fmt(m.unscanned_size)}</b></span>` +
    `<span class="${m.disk_free < 15*1024**3 ? "free-warn" : ""}">□ 剩余 <b>${fmt(m.disk_free)}</b> / ${fmt(m.disk_total)}</span>`;
  document.getElementById("legend").innerHTML = Object.entries(S).map(([k,s]) =>
    `<span class="chip"><span class="dot" style="background:color-mix(in srgb, ${s.bg} 32%, var(--surface))"></span>${s.icon} ${s.label}</span>`).join("");
}

(async () => {
  try {
    const p = await (await fetch("/api/ping")).json();
    SERVER = p.ok === true;
    AI_AVAIL = p.ai_available === true;
    AI_PROVIDER = p.ai_provider;
  } catch (e) { SERVER = false; }
  const pill = document.getElementById("modepill");
  pill.classList.toggle("live", SERVER);
  document.getElementById("modetext").textContent = SERVER
    ? `服务在线${AI_AVAIL ? " · AI: " + AI_PROVIDER : " · AI 未安装(可选)"}`
    : "只读模式 · 运行 python serve.py 解锁清理功能";
  if (SERVER) {
    document.getElementById("rescanpill").style.display = "";
    refreshQuarantine();
    loadCleanlog();
  }
  route();   // ping 结果出来后重渲染当前视图（浏览器/隔离区等依赖 SERVER 状态）
})();

async function refreshQuarantine() {
  try {
    const q = await api("/api/quarantine", {action: "status"});
    const pill = document.getElementById("qpill");
    if (q.total_bytes > 0) {
      pill.style.display = "";
      const age = q.oldest_days >= 1 ? `（最老 ${q.oldest_days} 天${q.oldest_days >= 30 ? " ⏰" : ""}）` : "";
      pill.innerHTML = `🗑️ 隔离区 ${fmt(q.total_bytes)}${age} <a onclick="location.hash='#/quarantine'">去处理</a>`;
    } else pill.style.display = "none";
  } catch (e) {}
}
async function loadCleanlog() {
  try {
    const d = await (await fetch("/api/cleanlog")).json();
    const scanTs = new Date(m.scanned_at.replace(" ", "T"));
    for (const e of (d.entries || []))
      if (new Date(e.ts.replace(" ", "T")) > scanTs)
        cleanedMap[e.path.toLowerCase()] = e;
    if (parseHash().view === "list") renderRows();
  } catch (e) {}
}
async function rescan() {
  const modal = document.getElementById("modal");
  modal.innerHTML = `<h3>重新扫描中…</h3>` + spin("扫描磁盘并生成新报告（约 20~60 秒），完成后自动刷新");
  openModal();
  try {
    const r = await api("/api/rescan", {});
    if (r.ok) { location.reload(); return; }
    modal.innerHTML = `<h3>扫描失败</h3><div class="notice bad">${esc(JSON.stringify(r))}</div>
      <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`;
  } catch (e) {
    modal.innerHTML = `<h3>扫描失败</h3><div class="notice bad">${esc(String(e))}</div>
      <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`;
  }
}

/* ---------- treemap（磁盘地图视图） ---------- */
function nodeSafety(node, path) {
  const ai = aiMap[path.toLowerCase()];
  if (node && node.rule) return node.rule.safety;
  if (ai) return ai.safety;
  return "none";
}
function findNode(path) {
  const parts = path.split("/").slice(1);
  let node = DATA.tree;
  for (const p of parts) {
    node = (node.dirs || {})[p];
    if (!node) return null;
  }
  return node;
}
function childrenOf(node, path) {
  const out = [];
  for (const [name, c] of Object.entries(node.dirs || {}))
    out.push({ name, size: c.size, node: c, path: path + "/" + name });
  for (const f of (node.big_files || []))
    out.push({ name: "📄 " + f.name, size: f.size, node: null, path: path + "/" + f.name, isFile: true });
  const accounted = out.reduce((a,x) => a + x.size, 0);
  if (node.other_dirs_size) out.push({ name: "(其他小目录)", size: node.other_dirs_size, node: null, path });
  const rest = node.size - accounted - (node.other_dirs_size||0);
  if (rest > 50*1024*1024) out.push({ name: "(散文件)", size: rest, node: null, path });
  return out.filter(x => x.size > 0).sort((a,b) => b.size - a.size);
}
function squarify(items, x, y, w, h, out) {
  if (!items.length) return;
  const total = items.reduce((a,i) => a + i.size, 0);
  let row = [], rest = items.slice();
  const scale = w*h/total;
  function worst(row, len) {
    const s = row.reduce((a,i) => a + i.size*scale, 0);
    let mx = 0;
    for (const i of row) {
      const a = i.size*scale;
      mx = Math.max(mx, Math.max((len*len*a)/(s*s), (s*s)/(len*len*a)));
    }
    return mx;
  }
  while (rest.length) {
    const len = Math.min(w, h);
    row.push(rest[0]);
    if (row.length > 1 && worst(row, len) > worst(row.slice(0,-1), len)) {
      row.pop(); layoutRow(row); row = []; continue;
    }
    rest.shift();
  }
  if (row.length) layoutRow(row);
  function layoutRow(row) {
    const s = row.reduce((a,i) => a + i.size*scale, 0);
    if (w >= h) {
      const cw = s/h; let cy = y;
      for (const i of row) { const ch = i.size*scale/cw; out.push({item:i, x, y:cy, w:cw, h:ch}); cy += ch; }
      x += cw; w -= cw;
    } else {
      const ch = s/w; let cx = x;
      for (const i of row) { const cw = i.size*scale/ch; out.push({item:i, x:cx, y, w:cw, h:ch}); cx += cw; }
      y += ch; h -= ch;
    }
  }
}
function renderTreemap() {
  const elTm = document.getElementById("treemap");
  if (!elTm.clientWidth) return;     // 视图未显示
  const cur = navStack[navStack.length-1];
  elTm.innerHTML = "";
  const W = elTm.clientWidth, H = elTm.clientHeight;
  let items = childrenOf(cur.node, cur.path);
  if (navStack.length === 1 && m.unscanned_size > 0)
    items.push({ name: "🔐 扫描不到的区域", size: m.unscanned_size, node: null,
                 path: cur.path + "/(系统保护区)", pseudo: true });
  items.sort((a,b) => b.size - a.size);
  const rects = [];
  squarify(items, 0, 0, W, H, rects);
  const GAP = 2;
  for (const r of rects) {
    const it = r.item;
    const safety = it.pseudo ? "none" : (it.node ? nodeSafety(it.node, it.path) : "none");
    const s = S[safety];
    const div = el("div", {className: "block", tabindex: "0"});
    div.style.cssText = `left:${r.x+GAP/2}px; top:${r.y+GAP/2}px; width:${Math.max(0,r.w-GAP)}px; height:${Math.max(0,r.h-GAP)}px;` +
      `background:color-mix(in srgb, ${s.bg} 30%, var(--surface));`;
    if (r.w > 55 && r.h > 26)
      div.innerHTML = `<div class="lb">${s.icon} ${esc(it.name)}<span class="sz">${fmt(it.size)}</span></div>`;
    div.onmousemove = e => showTip(e, it, safety);
    div.onmouseleave = hideTip;
    div.onclick = e => { e.stopPropagation(); hideTip();
      showMapDetail(it, safety);
      if (it.node && Object.keys(it.node.dirs||{}).length) {
        navStack.push({name: it.name, node: it.node, path: it.path});
        renderTreemap();
      }
    };
    elTm.appendChild(div);
  }
  const cr = document.getElementById("crumbs");
  cr.innerHTML = "";
  navStack.forEach((n, i) => {
    if (i) cr.appendChild(document.createTextNode(" › "));
    if (i === navStack.length-1) cr.appendChild(el("b", {}, esc(n.name)));
    else cr.appendChild(el("a", {onclick: () => { navStack = navStack.slice(0, i+1); renderTreemap(); }}, esc(n.name)));
  });
}
const tip = document.getElementById("tip");
function showTip(e, it, safety) {
  const s = S[safety];
  const info = it.node && it.node.rule ? it.node.rule.title : (aiMap[it.path.toLowerCase()]||{}).title || "";
  tip.innerHTML = `<b>${esc(it.name)}</b> · ${fmt(it.size)}<br>` +
    `<span style="color:var(--ink2)">${esc(it.path)}</span><br>${s.icon} ${esc(info || s.label)}`;
  tip.style.display = "block";
  tip.style.left = Math.min(e.clientX + 14, window.innerWidth - 400) + "px";
  tip.style.top = (e.clientY + 14) + "px";
}
function hideTip() { tip.style.display = "none"; }
function showMapDetail(it, safety) {
  const s = S[safety];
  const rule = it.node && it.node.rule;
  const ai = aiMap[it.path.toLowerCase()];
  const title = (rule && rule.title) || (ai && ai.title) || it.name;
  const desc = (rule && rule.desc) || (ai && ai.desc) ||
    (it.pseudo ? "页面文件、系统还原点、商店应用等需要管理员权限才能读取的区域。"
               : "知识库暂未收录。可去文件浏览器逐项判定。");
  const act = (rule && rule.action) || (ai && ai.action) || "";
  const box = document.getElementById("mapdetail");
  box.innerHTML =
    `<h3>${esc(title)}${ai && !rule ? '<span class="aitag">AI 分析</span>' : ""}</h3>` +
    `<div class="path">${esc(it.path)}</div>` +
    `<div class="size">${fmt(it.size)}</div>` +
    `<div><span class="badge" style="color:${s.color}">${s.icon} ${s.label}</span></div>` +
    `<div class="desc">${esc(desc)}</div>` +
    (act ? `<div class="act"><b>清理方法：</b>${esc(act)}</div>` : "");
  if (!it.pseudo && !it.isFile) {
    const b = el("button", {className: "btn small ghost", onclick: () => gotoBrowse(it.path)},
                 "📂 在文件浏览器中打开");
    if (!SERVER) b.disabled = true;
    const wrap = el("div"); wrap.style.marginTop = "10px"; wrap.appendChild(b);
    box.appendChild(wrap);
  }
}

/* ---------- 清理清单视图 ---------- */
const rows = [];
{
  const seen = new Set();
  for (const f of DATA.findings) { rows.push({...f, src: "kb"}); seen.add(f.path.toLowerCase()); }
  for (const n of AI_NOTES.notes) if (!seen.has(n.path.toLowerCase())) {
    const size = (DATA.unknowns.find(u => u.path.toLowerCase() === n.path.toLowerCase()) || {}).size || n.size || 0;
    if (size < 50*1024*1024) continue;
    rows.push({ path: n.path, size, title: n.title, safety: n.safety, desc: n.desc, action: n.action, src: "ai" });
  }
}
const FILTERS = [["all","全部"],["safe","✅ 可放心清理"],["caution","⚠️ 需注意方法"],
  ["user","👤 个人文件"],["danger","🚫 别手动删"],["keep","🔒 保留勿删"],["ai","🤖 AI 分析项"]];
{
  const fb = document.getElementById("filters");
  for (const [k,l] of FILTERS) {
    const b = el("button", {className: "fbtn" + (k==="all"?" on":""),
      onclick: ev => { filter = k;
        document.querySelectorAll(".fbtn").forEach(x => x.classList.toggle("on", x === ev.currentTarget));
        renderRows(); }}, l);
    fb.appendChild(b);
  }
  document.getElementById("th-size").addEventListener("click", () => setSort("size"));
  document.getElementById("th-safety").addEventListener("click", () => setSort("safety"));
}
function setSort(key) {
  if (sortKey === key) sortDir = -sortDir;
  else { sortKey = key; sortDir = key === "size" ? -1 : 1; }
  renderRows();
}
function sortedRows() {
  const arr = rows.filter(r =>
    filter === "all" ? true : filter === "ai" ? r.src === "ai" : r.safety === filter);
  arr.sort((a,b) => {
    let v = 0;
    if (sortKey === "size") v = a.size - b.size;
    else v = (S[a.safety]||S.none).order - (S[b.safety]||S.none).order || b.size - a.size;
    return v * sortDir;
  });
  return arr;
}
function renderRows() {
  for (const k of ["size","safety"]) {
    const th = document.getElementById("th-" + k);
    th.classList.toggle("active", sortKey === k);
    th.querySelector(".arrow").textContent = sortKey === k ? (sortDir === -1 ? "▼" : "▲") : "▼";
  }
  const tb = document.getElementById("rows");
  tb.innerHTML = "";
  for (const r of sortedRows()) {
    const s = S[r.safety] || S.none;
    const cl = cleanedMap[r.path.toLowerCase()];
    const canCheck = !cl && r.safety !== "keep" && r.safety !== "danger";
    const tr = el("tr", {className: "frow" + (expanded.has(r.path) ? " open" : "")});
    if (cl) tr.style.opacity = ".55";
    const deltaHtml = (!cl && r.delta != null && Math.abs(r.delta) >= 10*1024*1024)
      ? `<div style="font-size:11px;font-weight:500;color:${r.delta > 0 ? "var(--keep)" : "var(--safe)"}">${r.delta > 0 ? "▲+" : "▼−"}${fmt(Math.abs(r.delta))}</div>` : "";
    tr.innerHTML =
      `<td></td>` +
      `<td class="num">${cl ? `<s>${fmt(r.size)}</s>` : fmt(r.size)}${deltaHtml}</td>` +
      `<td style="white-space:nowrap">${cl
        ? `<span class="badge" style="color:var(--safe)">✓ 已清理 ${fmt(cl.bytes)}</span>`
        : `<span class="badge" style="color:${s.color}">${s.icon} ${s.label}</span>`}</td>` +
      `<td><div class="t"><span class="caret">▶</span>${esc(r.title)}${r.src==="ai"?'<span class="aitag">AI 分析</span>':""}</div>` +
      `<div class="p">${esc(r.path)}</div>` +
      `<div class="d">${esc(r.desc)}</div>` +
      (r.action ? `<div class="a"><b>清理方法：</b>${esc(r.action)}</div>` : "") + `</td>`;
    if (canCheck) {
      const cb = el("input", {type: "checkbox"});
      cb.checked = basket.has(r.path);
      cb.addEventListener("click", e => { e.stopPropagation();
        cb.checked
          ? basket.set(r.path, {path: r.path, size: r.size, source: "list",
                                title: r.title, safety: r.safety, action: r.action})
          : basket.delete(r.path);
        renderBasket(); });
      tr.children[0].appendChild(cb);
    }
    tr.addEventListener("click", () => toggleDrawer(r));
    tb.appendChild(tr);
    if (expanded.has(r.path)) tb.appendChild(buildDrawer(r));
  }
}
function toggleDrawer(r) {
  expanded.has(r.path) ? expanded.delete(r.path) : expanded.add(r.path);
  renderRows();
  if (expanded.has(r.path) && SERVER && !detailCache[r.path]) fetchDetail(r);
}
function buildDrawer(r) {
  const tr = el("tr", {className: "drawer"});
  tr.dataset.path = r.path;
  const node = findNode(r.path);
  let sub = "";
  if (node) {
    const kids = childrenOf(node, r.path).slice(0, 8);
    const mx = Math.max(...kids.map(k => k.size), 1);
    sub = kids.map(k =>
      `<tr><td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(k.name)}</td>` +
      `<td class="num">${fmt(k.size)}</td>` +
      `<td style="width:35%"><div class="bar" style="width:${Math.max(2, k.size/mx*100)}%"></div></td></tr>`).join("");
  }
  const cached = detailCache[r.path];
  tr.innerHTML = `<td colspan="4"><div class="drawer-grid">` +
    `<div><h4>内部构成（来自扫描）</h4>` +
      (sub ? `<table class="mini">${sub}</table>` : `<div class="hint">此目录无 50MB 以上的子项。</div>`) +
      `<div style="margin-top:8px"><button class="btn small ghost" data-act="browse" ${SERVER?"":"disabled"}>📂 去文件浏览器逐项判定</button></div>` +
    `</div>` +
    `<div><h4>实时深挖 ${SERVER ? "" : "（需启动服务）"}</h4><div class="live">` +
      (cached ? liveHtml(cached) : (SERVER ? `<span class="spin"></span> 正在读取目录内容…` :
        `<div class="hint">用 serve.py 打开报告后这里显示最大文件、类型分布、最近使用时间。</div>`)) +
    `</div></div>` +
    `<div class="aibox" style="margin-top:14px">` + (r.aiText
      ? `<b>🤖 AI 深度分析</b>\n${esc(r.aiText)}`
      : `<button class="btn small ghost" data-act="ai" ${SERVER && AI_AVAIL ? "" : "disabled"}>🤖 生成 AI 深度分析</button>` +
        `<span class="hint" style="margin-left:8px">${SERVER && !AI_AVAIL ? "需安装 Claude Code / Codex / Gemini CLI（可选）" : "调用本机 AI 分析这个目录（约 10~30 秒）"}</span>`) +
    `</div></td>`;
  tr.addEventListener("click", e => {
    e.stopPropagation();
    const act = e.target.dataset && e.target.dataset.act;
    if (act === "browse") gotoBrowse(r.path);
    if (act === "ai") askAI(r);
  });
  return tr;
}
function liveHtml(d) {
  if (d.error) return `<div class="hint">${esc(d.error)}</div>`;
  let h = `<div class="hint" style="margin:0 0 6px">共 ${d.file_count.toLocaleString()}${d.truncated?"+":""} 个文件 · ` +
    `最近修改 ${esc(d.newest_mtime||"?")}（${d.days_since_change != null ? d.days_since_change + " 天前" : "?"}）</div>`;
  if (d.ext_stats && d.ext_stats.length) {
    const mx = Math.max(...d.ext_stats.map(x => x.size), 1);
    h += `<table class="mini">` + d.ext_stats.map(x =>
      `<tr><td>${esc(x.ext)}</td><td class="num">${fmt(x.size)}</td>` +
      `<td style="width:35%"><div class="bar" style="width:${Math.max(2,x.size/mx*100)}%"></div></td></tr>`).join("") + `</table>`;
  }
  if (d.top_files && d.top_files.length) {
    h += `<h4 style="margin-top:10px">最大文件</h4><table class="mini">` + d.top_files.slice(0,6).map(f =>
      `<tr><td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(f.path)}">${esc(f.path)}</td>` +
      `<td class="num">${fmt(f.size)}</td><td>${esc(f.mtime)}</td></tr>`).join("") + `</table>`;
  }
  return h;
}
async function fetchDetail(r) {
  try { detailCache[r.path] = await api("/api/detail", {path: r.path}); }
  catch (e) { detailCache[r.path] = {error: "读取失败: " + e}; }
  const dr = document.querySelector(`tr.drawer[data-path="${CSS.escape(r.path)}"] .live`);
  if (dr) dr.innerHTML = liveHtml(detailCache[r.path]);
}
async function askAI(r) {
  const box = document.querySelector(`tr.drawer[data-path="${CSS.escape(r.path)}"] .aibox`);
  if (box) box.innerHTML = `<span class="spin"></span> AI 正在分析这个目录…（10~30 秒）`;
  try {
    const res = await api("/api/ai", {path: r.path, context: {title: r.title, safety: r.safety, desc: r.desc, size: r.size}});
    r.aiText = res.text || res.error || "（无结果）";
  } catch (e) { r.aiText = "AI 分析失败: " + e; }
  renderRows();
}

/* ---------- 文件浏览器视图 ---------- */
function renderBrowse() {
  const path = expStack[expStack.length-1];
  const cr = document.getElementById("bcrumbs");
  cr.innerHTML = "";
  expStack.forEach((p, i) => {
    if (i) cr.appendChild(document.createTextNode(" › "));
    const label = i === 0 ? p : p.split("/").pop();
    if (i === expStack.length-1) cr.appendChild(el("b", {}, esc(label)));
    else cr.appendChild(el("a", {onclick: () => gotoBrowse(p)}, esc(label)));
  });
  const bt = document.getElementById("btable");
  if (!SERVER) {
    bt.innerHTML = `<div class="notice">文件浏览器需要本地服务：运行 <code>python serve.py</code> 后使用。</div>`;
    return;
  }
  const d = browseCache[path];
  if (!d) {
    bt.innerHTML = spin("正在读取并判定每一项…（大目录最多几秒）");
    api("/api/browse", {path}).then(res => { browseCache[path] = res; renderBrowse(); })
      .catch(e => { browseCache[path] = {error: String(e)}; renderBrowse(); });
    return;
  }
  if (d.error) {
    bt.innerHTML = `<div class="notice bad">${esc(d.error)}</div>`;
    document.getElementById("bsafescan").innerHTML = "";
    return;
  }
  // 安全汇总（懒加载，仅在浏览器视图根显示）
  renderSafeScanBlock(path);
  const unknownCount = d.entries.filter(e => !e.safety).length;
  const table = el("table", {className: "exp-table"});
  table.innerHTML = `<tr style="color:var(--muted);font-size:12px">
    <td></td><td>名称（点📁进入）</td><td>大小</td><td>修改日期</td><td>判定</td><td>理由 / 建议</td></tr>`;
  for (const e2 of d.entries) {
    const safety = e2.safety || "none";
    const why = e2.why || (safety === "none" ? "未识别——点下方'AI 判定'" : "");
    const s = S[safety] || S.none;
    const canDel = safety !== "keep" && safety !== "danger";
    const full = path + "/" + e2.name;
    const tr = el("tr");
    const tdCb = el("td");
    if (canDel) {
      const cb = el("input", {type: "checkbox"});
      cb.checked = basket.has(full);
      cb.addEventListener("click", () => {
        cb.checked
          ? basket.set(full, {path: full, size: e2.size, source: "browse",
                              title: e2.name, safety, base: path, name: e2.name})
          : basket.delete(full);
        renderBasket(); });
      tdCb.appendChild(cb);
    }
    tr.appendChild(tdCb);
    const tdNm = el("td", {className: "nm"});
    if (e2.is_dir) {
      const a = el("a", {onclick: () => gotoBrowse(full)}, "📁 " + esc(e2.name));
      tdNm.appendChild(a);
    } else tdNm.innerHTML = "📄 " + esc(e2.name);
    tdNm.title = full;
    tr.appendChild(tdNm);
    tr.appendChild(el("td", {className: "num"}, fmt(e2.size) + (e2.size_exact ? "" : "≈")));
    tr.appendChild(el("td", {}, esc(e2.mtime)));
    tr.appendChild(el("td", {style: "white-space:nowrap"},
      `<span class="badge" style="color:${s.color}">${s.icon} ${s.label}</span>` +
      ((e2.why||"").startsWith("（AI") ? '<span class="aitag">AI</span>' : "")));
    tr.appendChild(el("td", {className: "why"}, esc(why)));
    table.appendChild(tr);
  }
  bt.innerHTML = "";
  const wrap = el("div", {style: "overflow-x:auto"});
  wrap.appendChild(table);
  bt.appendChild(wrap);
  const foot = document.getElementById("bfoot");
  foot.innerHTML = "";
  foot.appendChild(el("span", {className: "hint"},
    `${d.entries.length} 项${unknownCount ? ` · ${unknownCount} 项未识别` : ""} · "≈"为估算 · 🔒/🚫级不可勾选`));
  const sp = el("span"); sp.style.flex = "1"; foot.appendChild(sp);
  if (unknownCount) {
    const b = el("button", {className: "btn small",
      onclick: () => aiJudge(path)}, `🤖 AI 判定未识别项（${unknownCount}）`);
    if (!AI_AVAIL) { b.disabled = true; b.title = "需安装 AI CLI（可选）"; }
    foot.appendChild(b);
  }
  if (expStack.length > 1)
    foot.appendChild(el("button", {className: "btn small ghost",
      onclick: () => gotoBrowse(expStack[expStack.length-2])}, "⬅ 返回上级"));
}
async function aiJudge(path) {
  const d = browseCache[path];
  if (!d || !d.entries) return;
  const unknown = d.entries.filter(e => !e.safety);
  toast(`AI 判定中（${unknown.length} 项，10~60 秒）…`);
  try {
    const r = await api("/api/ai_judge", {path, entries: unknown});
    if (r.verdicts) {
      delete browseCache[path];   // 服务端已入缓存，重新拉取即带 AI 判定
      renderBrowse();
      toast("AI 判定完成");
    } else toast(r.error || "AI 判定失败", true);
  } catch (e) { toast("AI 判定失败: " + e, true); }
}
function renderSafeScanBlock(path) {
  const box = document.getElementById("bsafescan");
  const d = safeScanCache[path];
  if (!d) {
    box.innerHTML = `<div class="notice" style="margin-bottom:10px"><span class="spin"></span>
      正在递归汇总此目录下所有「✅ 可放心清理」的项目…</div>`;
    api("/api/safe_scan", {path}).then(res => { safeScanCache[path] = res;
      if (expStack[expStack.length-1] === path) renderSafeScanBlock(path); })
      .catch(e => { safeScanCache[path] = {error: String(e)}; renderSafeScanBlock(path); });
    return;
  }
  if (d.error) { box.innerHTML = ""; return; }
  if (!d.items.length) {
    box.innerHTML = `<div class="hint" style="margin-bottom:10px">此目录下没有扫到可直接安全删除的项目。</div>`;
    return;
  }
  const det = el("details", {className: "fold card sunk", open: ""});
  const inBasket = d.items.filter(it => basket.has(it.path)).length;
  det.innerHTML = `<summary>✅ 安全可删汇总：${d.items.length} 项 · 合计 ${fmt(d.total)}${d.truncated ? "（超时截断）" : ""}${inBasket ? ` · 已选 ${inBasket}` : ""}</summary>`;
  const bar = el("div", {style: "display:flex;gap:10px;margin:8px 0"});
  bar.appendChild(el("button", {className: "btn small ghost", onclick: () => {
    for (const it of d.items) basket.set(it.path, {path: it.path, size: it.size,
      source: "safe", title: it.rel, safety: "safe"});
    renderBasket(); renderSafeScanBlock(path); renderBrowse();
  }}, "全部加入清理篮"));
  det.appendChild(bar);
  const sc = el("div", {className: "scrolly"});
  const table = el("table", {className: "exp-table"});
  for (const it of d.items) {
    const tr = el("tr");
    const tdCb = el("td");
    const cb = el("input", {type: "checkbox"});
    cb.checked = basket.has(it.path);
    cb.addEventListener("click", () => {
      cb.checked
        ? basket.set(it.path, {path: it.path, size: it.size, source: "safe", title: it.rel, safety: "safe"})
        : basket.delete(it.path);
      renderBasket(); });
    tdCb.appendChild(cb); tr.appendChild(tdCb);
    const nm = el("td", {className: "nm"}, (it.is_dir ? "📁 " : "📄 ") + esc(it.rel));
    nm.title = it.path; tr.appendChild(nm);
    tr.appendChild(el("td", {className: "num"}, fmt(it.size) + (it.size_exact ? "" : "≈")));
    tr.appendChild(el("td", {className: "why"}, esc(it.why || "")));
    table.appendChild(tr);
  }
  sc.appendChild(table); det.appendChild(sc);
  box.innerHTML = ""; box.appendChild(det); box.style.marginBottom = "10px";
}

/* ---------- 专项工具视图 ---------- */
function renderTools() {
  renderDupes();
  renderLeftovers();
}
function renderDupes() {
  const box = document.getElementById("dupebox");
  if (!SERVER) { box.innerHTML = `<div class="hint">需启动本地服务。</div>`; return; }
  if (!dupeData) {
    box.innerHTML = spin("扫描用户目录下 ≥10MB 的重复文件（最多 45 秒）…");
    api("/api/dupes", {}).then(r => { dupeData = r; renderDupes(); })
      .catch(e => { dupeData = {error: String(e)}; renderDupes(); });
    return;
  }
  const d = dupeData;
  if (d.error) { box.innerHTML = `<div class="notice bad">${esc(d.error)}</div>`; return; }
  if (!d.groups.length) {
    box.innerHTML = `<div class="hint">✅ 未发现 ≥10MB 的重复文件（扫描 ${d.scanned_files.toLocaleString()} 个文件）。</div>`;
    return;
  }
  box.innerHTML = "";
  const head = el("div", {style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px"});
  head.appendChild(el("span", {className: "hint"},
    `${d.groups.length} 组重复 · 合计可省 <b>${fmt(d.total_wasted)}</b>${d.truncated ? "（超时截断）" : ""}`));
  head.appendChild(el("button", {className: "btn small ghost", onclick: () => {
    for (const g of d.groups) g.files.slice(1).forEach(f =>
      basket.set(f.path, {path: f.path, size: g.size, source: "dupe", title: f.path.split("/").pop(), safety: "user"}));
    renderBasket(); renderDupes();
  }}, "每组保留 ⭐ 第一份，其余加入清理篮"));
  box.appendChild(head);
  for (const g of d.groups) {
    const card = el("div", {className: "card sunk"});
    card.innerHTML = `<b>${fmt(g.size)}</b> × ${g.files.length} 份 · 可省 ${fmt(g.wasted)}`;
    const table = el("table", {className: "exp-table", style: "margin-top:4px"});
    g.files.forEach((f, fi) => {
      const tr = el("tr");
      const tdCb = el("td");
      const cb = el("input", {type: "checkbox"});
      cb.checked = basket.has(f.path);
      cb.addEventListener("click", () => {
        cb.checked
          ? basket.set(f.path, {path: f.path, size: g.size, source: "dupe", title: f.path.split("/").pop(), safety: "user"})
          : basket.delete(f.path);
        renderBasket(); });
      tdCb.appendChild(cb); tr.appendChild(tdCb);
      const nm = el("td", {className: "nm", style: "max-width:560px"},
        (fi === 0 ? "⭐ " : "") + esc(f.path.replace(/^C:\/Users\/[^/]+\//, "~/")));
      nm.title = f.path; tr.appendChild(nm);
      tr.appendChild(el("td", {}, esc(f.mtime)));
      table.appendChild(tr);
    });
    card.appendChild(table);
    box.appendChild(card);
  }
}
function renderLeftovers() {
  const box = document.getElementById("leftbox");
  if (!SERVER) { box.innerHTML = `<div class="hint">需启动本地服务。</div>`; return; }
  if (!leftData) {
    box.innerHTML = spin("比对注册表已装程序与实际目录…");
    api("/api/leftovers", {}).then(r => { leftData = r; renderLeftovers(); })
      .catch(e => { leftData = {error: String(e)}; renderLeftovers(); });
    return;
  }
  const d = leftData;
  if (d.error) { box.innerHTML = `<div class="notice bad">${esc(d.error)}</div>`; return; }
  if (!d.items.length) {
    box.innerHTML = `<div class="hint">✅ 未发现疑似卸载残留（已装程序 ${d.installed_count} 个全对上号）。</div>`;
    return;
  }
  box.innerHTML = "";
  const table = el("table", {className: "exp-table"});
  table.innerHTML = `<tr style="color:var(--muted);font-size:12px">
    <td></td><td>目录（注册表里找不到对应程序）</td><td>大小</td><td>最后修改</td></tr>`;
  for (const it of d.items) {
    const tr = el("tr");
    const tdCb = el("td");
    const cb = el("input", {type: "checkbox"});
    cb.checked = basket.has(it.path);
    cb.addEventListener("click", () => {
      cb.checked
        ? basket.set(it.path, {path: it.path, size: it.size, source: "leftover", title: it.path.split("/").pop(), safety: "user"})
        : basket.delete(it.path);
      renderBasket(); });
    tdCb.appendChild(cb); tr.appendChild(tdCb);
    const nm = el("td", {className: "nm"}, "📁 " + esc(it.path));
    nm.title = it.path; tr.appendChild(nm);
    tr.appendChild(el("td", {className: "num"}, fmt(it.size) + (it.size_exact ? "" : "≈")));
    tr.appendChild(el("td", {}, esc(it.mtime)));
    table.appendChild(tr);
  }
  box.appendChild(table);
}

/* ---------- 隔离区视图 ---------- */
async function renderQuarantine() {
  const box = document.getElementById("qbox");
  if (!SERVER) { box.innerHTML = `<div class="hint" style="margin-top:10px">需启动本地服务。</div>`; return; }
  box.innerHTML = spin("正在逐个文件复检隔离区内容…");
  let d;
  try { d = await api("/api/quarantine_review", {}); }
  catch (e) { box.innerHTML = `<div class="notice bad">${esc(String(e))}</div>`; return; }
  if (!d.batches || !d.batches.length) {
    box.innerHTML = `<div class="hint" style="margin-top:10px">隔离区是空的。</div>`;
    refreshQuarantine(); return;
  }
  box.innerHTML = "";
  const anySus = d.batches.some(b => b.suspicious.length);
  for (const b of d.batches) {
    const date = `${b.batch.slice(0,4)}-${b.batch.slice(4,6)}-${b.batch.slice(6,8)} ${b.batch.slice(9,11)}:${b.batch.slice(11,13)}`;
    const card = el("div", {className: "card"});
    const head = el("div", {className: "cardhead"});
    head.appendChild(el("b", {}, `批次 ${date}`));
    head.appendChild(el("span", {className: "hint"}, `${b.file_count.toLocaleString()} 个文件 · ${fmt(b.total_bytes)}`));
    const sp = el("span"); sp.style.flex = "1"; head.appendChild(sp);
    if (b.has_manifest)
      head.appendChild(el("button", {className: "btn small ghost", onclick: () => restoreBatch(b.batch)}, "↩ 还原此批次"));
    else head.appendChild(el("span", {className: "hint"}, "（无清单，只能手动还原）"));
    head.appendChild(el("button", {className: "btn small danger", onclick: () => emptyBatch(b.batch)}, "清空此批次"));
    card.appendChild(head);
    if (b.sources.length)
      card.appendChild(el("div", {className: "hint"}, "来源：" + b.sources.map(esc).join("、")));
    if (b.suspicious.length) {
      card.appendChild(el("div", {className: "notice bad", style: "margin-top:8px"},
        `⚠️ 复检发现 ${b.suspicious.length} 个不可再生特征文件——清空前先确认：`));
      const table = el("table", {className: "exp-table", style: "margin-top:4px"});
      for (const s2 of b.suspicious.slice(0, 10)) {
        const tr = el("tr");
        const nm = el("td", {className: "nm"}, "📄 " + esc(s2.file.split("\\").pop()));
        nm.title = s2.file; tr.appendChild(nm);
        tr.appendChild(el("td", {className: "num"}, fmt(s2.size)));
        tr.appendChild(el("td", {className: "why"}, esc(s2.reason)));
        table.appendChild(tr);
      }
      card.appendChild(table);
    } else {
      card.appendChild(el("div", {className: "hint", style: "margin-top:6px"},
        `✅ 复检通过：全部为可再生类型（缓存/日志/临时文件特征）`));
    }
    box.appendChild(card);
  }
  const foot = el("div", {style: "margin-top:14px;display:flex;justify-content:flex-end"});
  foot.appendChild(el("button", {className: "btn danger",
    onclick: () => emptyBatch(null)}, anySus ? "⚠️ 仍要清空全部" : "清空全部批次"));
  box.appendChild(foot);
}
async function emptyBatch(batch) {
  const what = batch ? `批次 ${batch}` : "全部批次";
  if (!confirm(`将永久删除隔离区${what}（不可恢复）。确定？`)) return;
  const r = await api("/api/quarantine", {action: "empty", batch});
  toast("已清空，释放 " + fmt(r.freed_bytes || 0));
  refreshQuarantine(); renderQuarantine();
}
async function restoreBatch(batch) {
  if (!confirm(`将把批次 ${batch} 的所有文件按清单放回原位置。确定？`)) return;
  const r = await api("/api/quarantine_restore", {batch});
  let msg = `已还原 ${r.restored} 项（${fmt(r.restored_bytes||0)}）`;
  if (r.skipped_exists && r.skipped_exists.length) msg += `；${r.skipped_exists.length} 项原位已有同名文件，保留在隔离区`;
  if (r.failed && r.failed.length) msg += `；失败 ${r.failed.length} 项`;
  toast(msg);
  refreshQuarantine(); renderQuarantine();
}

/* ---------- 全局清理篮 ---------- */
const SRC_LABEL = {list: "清单", browse: "浏览器", safe: "安全汇总", dupe: "重复文件", leftover: "卸载残留"};
function renderBasket() {
  const bar = document.getElementById("basketbar");
  bar.classList.toggle("show", basket.size > 0);
  if (!basket.size) { document.getElementById("basketlist").classList.remove("show"); return; }
  const items = [...basket.values()];
  const total = items.reduce((a,i) => a + i.size, 0);
  const bySrc = {};
  for (const i of items) bySrc[i.source] = (bySrc[i.source] || 0) + 1;
  const srcTxt = Object.entries(bySrc).map(([k,n]) => `${SRC_LABEL[k]}${n}`).join(" + ");
  document.getElementById("bsum").innerHTML =
    `🧺 清理篮：<b>${basket.size}</b> 项 · <b>${fmt(total)}</b>　<span class="hint">(${srcTxt})</span>`;
  document.getElementById("submitbtn").textContent = SERVER ? "提交清理" : "生成清理计划";
  const bl = document.getElementById("basketitems");
  bl.innerHTML = "";
  for (const i of items.sort((a,b) => b.size - a.size)) {
    const row = el("div", {className: "brow"});
    row.appendChild(el("span", {className: "badge"}, SRC_LABEL[i.source]));
    row.appendChild(el("span", {className: "p"}, esc(i.path)));
    row.appendChild(el("b", {}, fmt(i.size)));
    row.appendChild(el("a", {onclick: () => { basket.delete(i.path); renderBasket(); route(); }}, "移出"));
    bl.appendChild(row);
  }
}
function toggleBasketList() { document.getElementById("basketlist").classList.toggle("show"); }
function clearBasket() { basket.clear(); renderBasket(); route(); }

async function submitBasket() {
  if (!basket.size) return;
  const items = [...basket.values()];
  // 重复文件防呆：每组必须留一份
  if (dupeData && dupeData.groups) for (const g of dupeData.groups) {
    if (g.files.length && g.files.every(f => basket.has(f.path)))
      return toast("有一组重复文件被全选了，每组至少要留一份：" + g.files[0].path, true);
  }
  const modal = document.getElementById("modal");
  if (!SERVER) {
    let txt = "===== C 盘清理计划 =====\n\n";
    for (const i of items)
      txt += `[${(S[i.safety]||S.none).label}] ${i.path} (${fmt(i.size)})\n  ${i.title}\n\n`;
    modal.innerHTML = `<h3>清理计划（只读模式）</h3>
      <textarea style="width:100%;height:260px;background:var(--sunken);color:var(--ink);border:1px solid var(--border);border-radius:8px;padding:10px;font:12px/1.5 Consolas,monospace" onclick="this.select()">${esc(txt)}</textarea>
      <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`;
    openModal(); return;
  }
  const listSafe = items.filter(i => i.source === "list" && i.safety === "safe");
  const listManual = items.filter(i => i.source === "list" && i.safety !== "safe");
  const browseItems = items.filter(i => i.source === "browse");
  const pathItems = items.filter(i => ["safe","dupe","leftover"].includes(i.source));
  modal.innerHTML = `<h3>安全检查</h3>` + spin("正在检查是否有程序正在这些目录里运行…");
  openModal();
  const occ = {};
  if (listSafe.length) {
    try {
      const pre = await api("/api/precheck", {paths: listSafe.map(i => i.path)});
      for (const p of pre.results) if (p.occupied) occ[p.path] = p;
    } catch (e) {}
  }
  const ready = listSafe.filter(i => !occ[i.path]);
  const blocked = listSafe.filter(i => occ[i.path]);
  const autoCount = ready.length + browseItems.length + pathItems.length;
  const autoBytes = [...ready, ...browseItems, ...pathItems].reduce((a,i) => a + i.size, 0);
  modal.innerHTML = `<h3>确认清理</h3>` +
    (autoCount ? `<div class="notice">将清理 <b>${autoCount}</b> 项 · 约 <b>${fmt(autoBytes)}</b>，
      默认先移入<b>隔离区</b>（可反悔，去"隔离区"页复检后清空才真正释放空间）。</div>` : "") +
    [...ready, ...browseItems, ...pathItems].slice(0, 30).map(i =>
      `<div class="mrow"><span class="badge">${SRC_LABEL[i.source]}</span> <b>${esc(i.title)}</b> · ${fmt(i.size)}
       <div class="p2">${esc(i.path)}</div></div>`).join("") +
    (autoCount > 30 ? `<div class="hint">…等 ${autoCount} 项</div>` : "") +
    (blocked.length ? `<div class="notice bad" style="margin-top:10px">⛔ ${blocked.length} 项有程序正在其中运行，本轮已排除：</div>` +
      blocked.map(i => `<div class="mrow"><b>${esc(i.title)}</b><div class="p2">正在运行：${esc(occ[i.path].procs.map(x => x.name).join("、"))}——关闭相关软件后再提交</div></div>`).join("") : "") +
    (listManual.length ? `<div class="notice" style="margin-top:10px">✋ ${listManual.length} 项需按方法手动处理（工具不代劳）：</div>` +
      listManual.map(i => `<div class="mrow"><b>${esc(i.title)}</b> · ${fmt(i.size)}<div class="p2">${esc(i.action || "见清单说明")}</div></div>`).join("") : "") +
    `<label style="display:flex;gap:8px;align-items:center;margin-top:14px;font-size:13px">
       <input type="checkbox" id="permcb"> 跳过隔离区，直接永久删除（快，但不可反悔）</label>
    <div class="foot">
      <button class="btn ghost" onclick="closeModal()">再想想</button>
      ${autoCount ? `<button class="btn" id="doSubmitBtn">开始清理 ${autoCount} 项</button>` : ""}
    </div>`;
  const btn = document.getElementById("doSubmitBtn");
  if (btn) btn.addEventListener("click", () => doSubmit(ready, browseItems, pathItems));
}
async function doSubmit(ready, browseItems, pathItems) {
  const permanent = document.getElementById("permcb").checked;
  const modal = document.getElementById("modal");
  modal.innerHTML = `<h3>清理中…</h3>` + spin(permanent ? "正在删除…" : "正在移入隔离区，大目录可能需要一两分钟");
  const results = [];
  let total = 0;
  try {
    if (ready.length) {
      const r = await api("/api/clean", {paths: ready.map(i => i.path), permanent});
      for (const x of r.results) {
        results.push({label: x.path, status: x.status, bytes: x.bytes || 0,
                      note: x.note || (x.skipped_inuse ? `${x.skipped_inuse} 个占用文件已跳过` : "")});
        if (x.status === "完成") { cleanedMap[x.path.toLowerCase()] = {bytes: x.bytes || 0}; basket.delete(x.path); }
      }
      total += r.total_bytes || 0;
    }
    const byBase = {};
    for (const i of browseItems) (byBase[i.base] = byBase[i.base] || []).push(i);
    for (const [base, arr] of Object.entries(byBase)) {
      const r = await api("/api/clean_items", {base, names: arr.map(i => i.name), permanent});
      for (const x of r.results) {
        results.push({label: base + "/" + x.name, status: x.status, bytes: x.bytes || 0, note: x.note || ""});
        if (x.status === "完成") basket.delete(base + "/" + x.name);
      }
      total += r.total_bytes || 0;
    }
    if (pathItems.length) {
      const r = await api("/api/clean_paths", {paths: pathItems.map(i => i.path), permanent});
      for (const x of r.results) {
        results.push({label: x.path, status: x.status, bytes: x.bytes || 0, note: x.note || ""});
        if (x.status === "完成") basket.delete(x.path);
      }
      total += r.total_bytes || 0;
    }
  } catch (e) {
    modal.innerHTML = `<h3>出错了</h3><div class="notice bad">${esc(String(e))}</div>
      <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`;
    return;
  }
  // 缓存失效：目录内容已变
  for (const k of Object.keys(browseCache)) delete browseCache[k];
  for (const k of Object.keys(safeScanCache)) delete safeScanCache[k];
  dupeData = null; leftData = null;
  const bad = results.filter(r => r.status !== "完成");
  modal.innerHTML = `<h3>清理完成</h3>
    <div class="notice">${permanent ? "已永久删除。" : "已移入隔离区（此时磁盘空间尚未释放）——确认无误后去「隔离区」页复检并清空。"}</div>` +
    results.slice(0, 40).map(r => `<div class="mrow">
      <span class="${r.status==="完成"?"ok":"bad"}">${r.status==="完成"?"✔":"✖"} ${esc(r.status)}</span>
      <b>${esc(r.label)}</b>${r.bytes ? " · " + fmt(r.bytes) : ""}${r.note ? `<div class="p2">${esc(r.note)}</div>` : ""}</div>`).join("") +
    `<div style="margin-top:10px;font-size:15px">合计处理 <b>${fmt(total)}</b>${bad.length ? ` · ${bad.length} 项未处理` : ""}</div>
    <div class="foot">
      <button class="btn ghost" onclick="closeModal();location.hash='#/quarantine'">去隔离区查看</button>
      <button class="btn small" onclick="closeModal();rescan()">🔄 重新扫描更新报告</button>
      <button class="btn ghost" onclick="closeModal()">完成</button>
    </div>`;
  renderBasket(); route(); refreshQuarantine();
}

/* ---------- modal ---------- */
function openModal() { document.getElementById("overlay").classList.add("show"); }
function closeModal() { document.getElementById("overlay").classList.remove("show"); }
document.getElementById("overlay").addEventListener("click", e => {
  if (e.target.id === "overlay") closeModal();
});

/* ---------- 初始化 ---------- */
navStack = [{ name: "C:", node: DATA.tree, path: "C:" }];
window.addEventListener("resize", () => { if (parseHash().view === "map") renderTreemap(); });
route();
