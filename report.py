# -*- coding: utf-8 -*-
"""
report.py — 生成交互式 HTML 分析报告 (v1.1)

单文件 HTML。用 serve.py 打开（http://127.0.0.1:8756）时具备完整能力：
提交清理、目录深挖、AI 按需分析；直接双击打开（file://）则退化为只读报告。

界面：容量条 + treemap 磁盘地图 + 可排序决策表（点表头排序）+ 行内详情抽屉 + 底部操作栏。
"""
import sys
import json
import os

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEMPLATE = r"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>C盘清理分析报告</title>
<style>
:root {
  color-scheme: light;
  --page: #f7f6f3; --surface: #fdfdfc; --sunken: #f1f0ec;
  --ink: #1a1915; --ink2: #55534c; --muted: #8b887f;
  --grid: #e3e1d9; --border: rgba(26,25,21,.11);
  --accent: #2a78d6; --accent-ink: #ffffff;
  --safe: #0a8a0a; --caution: #9a6a00; --danger: #b84a20; --keep: #c22f2f; --user: #2a78d6; --none: #8b887f;
  --safe-bg: #0ca30c; --caution-bg: #fab219; --danger-bg: #ec835a;
  --keep-bg: #d03b3b; --user-bg: #2a78d6; --none-bg: #8b887f;
  --shadow: 0 10px 30px rgba(26,25,21,.12);
}
:root[data-theme="dark"], :root.dark { color-scheme: dark; }
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --page: #121210; --surface: #1c1c1a; --sunken: #161614;
    --ink: #f2f1ec; --ink2: #bdbbb1; --muted: #85837a;
    --grid: #2d2d2a; --border: rgba(242,241,236,.12);
    --safe: #3ec43e; --caution: #fab219; --danger: #f09468; --keep: #ef6363; --user: #4a90e2;
    --shadow: 0 10px 30px rgba(0,0,0,.5);
  }
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } * { transition: none !important; } }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 14px/1.65 system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
.wrap { max-width: 1320px; margin: 0 auto; padding: 26px 22px 120px; }
.eyebrow { font-size: 11px; letter-spacing: .14em; color: var(--muted); text-transform: uppercase; }
h1 { font-size: 24px; margin: 2px 0 4px; letter-spacing: -.01em; }
.sub { color: var(--ink2); font-size: 13px; }
.statusline { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 12.5px; color: var(--ink2); }
.pill { display: inline-flex; align-items: center; gap: 5px; padding: 2px 10px; border-radius: 999px;
  border: 1px solid var(--border); background: var(--surface); font-size: 12px; }
.pill .dot2 { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); }
.pill.live .dot2 { background: var(--safe-bg); }

/* 容量条 */
.capacity { margin: 20px 0 8px; }
.capbar { display: flex; height: 26px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }
.capbar div { min-width: 2px; }
.capbar .used { background: var(--user-bg); opacity: .85; }
.capbar .hidden-part { background: repeating-linear-gradient(45deg, var(--muted), var(--muted) 4px, transparent 4px, transparent 8px); opacity: .5; }
.capbar .free { background: var(--sunken); }
.caplegend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 6px; font-size: 12.5px; color: var(--ink2); }
.caplegend b { color: var(--ink); font-variant-numeric: tabular-nums; }
.caplegend .free-warn b { color: var(--keep); }

.legend { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 16px 0 10px; font-size: 13px; color: var(--ink2); }
.legend .chip { display: inline-flex; align-items: center; gap: 6px; }
.dot { width: 11px; height: 11px; border-radius: 3px; display: inline-block; border: 1px solid var(--border); }

.main { display: grid; grid-template-columns: 1fr 350px; gap: 14px; align-items: start; }
@media (max-width: 940px) { .main { grid-template-columns: 1fr; } }
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px; }
.crumbs { font-size: 13px; margin-bottom: 8px; color: var(--ink2); min-height: 20px; }
.crumbs a { color: var(--accent); cursor: pointer; text-decoration: none; }
.crumbs a:hover, .crumbs a:focus-visible { text-decoration: underline; }
#treemap { position: relative; width: 100%; height: 540px; }
.block { position: absolute; overflow: hidden; border-radius: 4px; cursor: pointer;
  border: 1px solid var(--border); }
.block:hover, .block:focus-visible { filter: brightness(.92); outline: none; }
.block .lb { padding: 3px 7px; font-size: 12px; line-height: 1.35; color: var(--ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.block .lb .sz { color: var(--ink2); font-size: 11px; display: block; font-variant-numeric: tabular-nums; }
#tip { position: fixed; pointer-events: none; z-index: 40; background: var(--surface);
  border: 1px solid var(--border); border-radius: 9px; padding: 8px 11px; font-size: 12px;
  box-shadow: var(--shadow); max-width: 380px; display: none; }
.hint { color: var(--muted); font-size: 12.5px; margin-top: 8px; }

#detail h3 { margin: 0 0 2px; font-size: 15px; word-break: break-all; }
#detail .path { color: var(--muted); font-size: 12px; word-break: break-all; }
#detail .size { font-size: 28px; font-weight: 650; margin: 8px 0; letter-spacing: -.02em; }
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border-radius: 999px;
  font-size: 12px; border: 1px solid var(--border); background: var(--page); white-space: nowrap; }
#detail .desc { margin: 10px 0; color: var(--ink2); font-size: 13.5px; }
#detail .act { background: var(--sunken); border-radius: 9px; padding: 9px 11px; font-size: 13px; }

.section { margin-top: 30px; }
.section-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; margin-bottom: 12px; }
.section h2 { font-size: 18px; margin: 0; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.fbtn { border: 1px solid var(--border); background: var(--surface); color: var(--ink2);
  border-radius: 999px; padding: 4px 13px; font-size: 13px; cursor: pointer; }
.fbtn:hover { border-color: var(--muted); }
.fbtn.on { background: var(--ink); color: var(--page); border-color: var(--ink); }

.tablewrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 14px; background: var(--surface); }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th, td { padding: 9px 12px; text-align: left; border-top: 1px solid var(--grid); vertical-align: top; }
thead th { position: sticky; top: 0; background: var(--sunken); color: var(--ink2); font-weight: 600;
  border-top: none; z-index: 2; font-size: 12.5px; }
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable:hover { color: var(--ink); }
th.sortable .arrow { opacity: .35; font-size: 10px; margin-left: 3px; }
th.sortable.active { color: var(--ink); }
th.sortable.active .arrow { opacity: 1; }
td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; font-weight: 650; }
tr.frow { cursor: pointer; }
tr.frow:hover { background: color-mix(in srgb, var(--accent) 5%, transparent); }
tr.frow.open { background: color-mix(in srgb, var(--accent) 8%, transparent); }
td .t { font-weight: 600; }
td .p { color: var(--muted); font-size: 12px; word-break: break-all; }
td .d { color: var(--ink2); margin-top: 2px; }
td .a { margin-top: 4px; font-size: 12.5px; color: var(--ink2); }
td .a b, .drawer b { color: var(--ink); }
.caret { display: inline-block; transition: transform .15s; color: var(--muted); margin-right: 4px; }
tr.frow.open .caret { transform: rotate(90deg); }
.aitag { font-size: 11px; color: var(--accent); border: 1px solid var(--accent);
  border-radius: 4px; padding: 0 4px; margin-left: 6px; white-space: nowrap; }

/* 详情抽屉 */
tr.drawer > td { background: var(--sunken); padding: 14px 16px 16px 44px; }
.drawer-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 940px) { .drawer-grid { grid-template-columns: 1fr; } }
.drawer h4 { margin: 0 0 6px; font-size: 12px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
.mini { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.mini td { padding: 3px 6px; border: none; }
.mini td.num { font-weight: 500; }
.mini .bar { height: 6px; border-radius: 3px; background: var(--accent); opacity: .55; }
.drawer .aibox { grid-column: 1 / -1; background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 14px; font-size: 13.5px; white-space: pre-wrap; }
.btn { background: var(--accent); color: var(--accent-ink); border: none; border-radius: 9px;
  padding: 8px 18px; font-size: 14px; cursor: pointer; font-weight: 600; }
.btn:hover { filter: brightness(1.08); }
.btn:disabled { opacity: .5; cursor: default; }
.btn.ghost { background: var(--surface); color: var(--ink); border: 1px solid var(--border); font-weight: 500; }
.btn.small { padding: 5px 12px; font-size: 13px; border-radius: 7px; }
.btn.danger { background: var(--keep-bg); }
.spin { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border);
  border-top-color: var(--accent); border-radius: 50%; animation: sp 1s linear infinite; vertical-align: -2px; }
@keyframes sp { to { transform: rotate(360deg); } }

/* 底部操作栏 */
#actionbar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 30;
  background: var(--surface); border-top: 1px solid var(--border);
  box-shadow: 0 -6px 24px rgba(0,0,0,.10); transform: translateY(110%); transition: transform .2s; }
#actionbar.show { transform: none; }
#actionbar .inner { max-width: 1320px; margin: 0 auto; padding: 12px 22px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
#actionbar .sum { font-size: 14px; }
#actionbar .sum b { font-size: 17px; font-variant-numeric: tabular-nums; }

/* 弹窗 */
#overlay { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 50;
  display: none; align-items: center; justify-content: center; padding: 20px; }
#overlay.show { display: flex; }
#modal { background: var(--surface); border-radius: 16px; max-width: 640px; width: 100%;
  max-height: 82vh; overflow-y: auto; padding: 22px 24px; box-shadow: var(--shadow); }
#modal.wide { max-width: 980px; }
.exp-crumbs { font-size: 13px; color: var(--ink2); margin: 4px 0 10px; word-break: break-all; }
.exp-crumbs a { color: var(--accent); cursor: pointer; }
.exp-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.exp-table td { padding: 6px 8px; border-top: 1px solid var(--grid); vertical-align: top; }
.exp-table .nm { font-weight: 600; white-space: nowrap; max-width: 260px; overflow: hidden; text-overflow: ellipsis; }
.exp-table .nm a { color: var(--accent); cursor: pointer; text-decoration: none; }
.exp-table .nm a:hover { text-decoration: underline; }
.exp-table .why { color: var(--ink2); font-size: 12.5px; }
.exp-table td.num { font-weight: 500; }
#modal h3 { margin: 0 0 10px; font-size: 17px; }
#modal .mrow { padding: 8px 0; border-top: 1px solid var(--grid); font-size: 13.5px; }
#modal .mrow .p2 { color: var(--muted); font-size: 12px; word-break: break-all; }
#modal .foot { display: flex; gap: 10px; justify-content: flex-end; margin-top: 16px; flex-wrap: wrap; }
.notice { background: var(--sunken); border-radius: 10px; padding: 10px 13px; font-size: 13px; color: var(--ink2); }
.ok { color: var(--safe); } .bad { color: var(--keep); }
input[type=checkbox] { width: 15px; height: 15px; accent-color: var(--accent); cursor: pointer; }
</style>

<div class="wrap">
  <div class="eyebrow">C-CLEANER · 磁盘分析</div>
  <h1>C盘清理分析报告</h1>
  <div class="sub" id="meta"></div>
  <div class="statusline">
    <span class="pill" id="modepill"><span class="dot2"></span><span id="modetext">检测服务中…</span></span>
    <span class="pill" id="qpill" style="display:none"></span>
    <span class="pill" id="rescanpill" style="display:none"><a style="color:var(--accent);cursor:pointer" onclick="rescan()">🔄 重新扫描</a></span>
    <span class="pill" id="dupepill" style="display:none"><a style="color:var(--accent);cursor:pointer" onclick="openDupes()">🔁 重复文件</a></span>
    <span class="pill" id="leftpill" style="display:none"><a style="color:var(--accent);cursor:pointer" onclick="openLeftovers()">🧩 卸载残留</a></span>
  </div>

  <div class="capacity">
    <div class="capbar" id="capbar"></div>
    <div class="caplegend" id="caplegend"></div>
  </div>

  <div class="legend" id="legend"></div>

  <div class="main">
    <div class="panel">
      <div class="crumbs" id="crumbs"></div>
      <div id="treemap"></div>
      <div class="hint">点击色块进入下一级，点击上方路径返回。颜色 = 安全等级（见图例）；灰色 = 未识别。</div>
    </div>
    <div class="panel" id="detail"><div class="hint">👈 点击左侧色块查看详情</div></div>
  </div>

  <div class="section">
    <div class="section-head">
      <h2>清理决策清单</h2>
      <span class="hint">点击表头排序 · 点击行展开详细分析 · 勾选后在底部提交清理</span>
    </div>
    <div class="filters" id="filters"></div>
    <div class="tablewrap"><table>
      <thead><tr>
        <th style="width:34px"></th>
        <th class="sortable" id="th-size" onclick="setSort('size')">大小 <span class="arrow">▼</span></th>
        <th class="sortable" id="th-safety" onclick="setSort('safety')">安全等级 <span class="arrow">▼</span></th>
        <th>项目 / 说明 / 清理方法</th>
      </tr></thead>
      <tbody id="rows"></tbody>
    </table></div>
  </div>
</div>

<div id="actionbar"><div class="inner">
  <span class="sum" id="absum"></span>
  <span style="flex:1"></span>
  <button class="btn ghost" onclick="clearSel()">取消全选</button>
  <button class="btn" id="submitbtn" onclick="submitClean()">提交清理</button>
</div></div>

<div id="overlay"><div id="modal"></div></div>
<div id="tip"></div>

<script>
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

let SERVER = false;

function fmt(b) {
  if (b >= 1024**3) return (b/1024**3).toFixed(2) + " GB";
  if (b >= 1024**2) return (b/1024**2).toFixed(1) + " MB";
  return (b/1024).toFixed(0) + " KB";
}
function esc(s) { return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;"); }
async function api(ep, body) {
  const r = await fetch(ep, { method: "POST", headers: {"Content-Type":"application/json"},
                              body: JSON.stringify(body || {}) });
  return r.json();
}

/* ---------- 顶部 ---------- */
const m = DATA.meta;
document.getElementById("meta").textContent =
  `${m.target} · 扫描于 ${m.scanned_at} · ${m.file_count.toLocaleString()} 个文件 · 耗时 ${m.elapsed_sec} 秒`;

const capbar = document.getElementById("capbar");
const segs = [
  ["used", m.scanned_size, "已扫描分析"],
  ["hidden-part", m.unscanned_size, "扫描不到（页面文件/还原点）"],
  ["free", m.disk_free, "剩余空间"],
];
capbar.innerHTML = segs.map(([cls, v]) =>
  `<div class="${cls}" style="flex:${Math.max(v,1)}" title="${fmt(v)}"></div>`).join("");
document.getElementById("caplegend").innerHTML =
  `<span>■ 已扫描 <b>${fmt(m.scanned_size)}</b></span>` +
  `<span>▨ 扫描不到 <b>${fmt(m.unscanned_size)}</b></span>` +
  `<span class="${m.disk_free < 15*1024**3 ? "free-warn" : ""}">□ 剩余 <b>${fmt(m.disk_free)}</b> / ${fmt(m.disk_total)}</span>`;

document.getElementById("legend").innerHTML = Object.entries(S).map(([k,s]) =>
  `<span class="chip"><span class="dot" style="background:color-mix(in srgb, ${s.bg} 32%, var(--surface))"></span>${s.icon} ${s.label}</span>`).join("");

/* ---------- 服务探测 ---------- */
(async () => {
  try {
    const r = await fetch("/api/ping");
    SERVER = (await r.json()).ok === true;
  } catch (e) { SERVER = false; }
  const pill = document.getElementById("modepill");
  pill.classList.toggle("live", SERVER);
  document.getElementById("modetext").textContent = SERVER
    ? "服务在线 · 可提交清理 / AI 深挖"
    : "只读模式 · 运行 python serve.py 解锁清理功能";
  if (SERVER) {
    document.getElementById("rescanpill").style.display = "";
    document.getElementById("dupepill").style.display = "";
    document.getElementById("leftpill").style.display = "";
    refreshQuarantine();
    loadCleanlog();
  }
})();

/* ---------- 重复文件查找（Czkawka 思路） ---------- */
let dupeData = null, dupeSel = new Set();
async function openDupes() {
  const modal = document.getElementById("modal");
  modal.classList.add("wide");
  modal.innerHTML = `<h3>🔁 重复文件查找</h3><div style="padding:22px;text-align:center">
    <span class="spin"></span><div class="hint" style="margin-top:8px">正在扫描用户目录下 ≥10MB 的重复文件（按内容指纹比对，最多 45 秒）…</div></div>`;
  openModal();
  if (!dupeData) {
    try { dupeData = await api("/api/dupes", {}); }
    catch (e) { dupeData = {error: String(e)}; }
  }
  renderDupes();
}
function renderDupes() {
  const modal = document.getElementById("modal");
  const d = dupeData;
  if (d.error) { modal.innerHTML = `<h3>🔁 重复文件查找</h3><div class="notice bad">${esc(d.error)}</div>
    <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`; return; }
  if (!d.groups.length) {
    modal.innerHTML = `<h3>🔁 重复文件查找</h3><div class="notice">✅ 未发现 ≥10MB 的重复文件（扫描了 ${d.scanned_files.toLocaleString()} 个文件）。</div>
      <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`; return;
  }
  const cards = d.groups.map((g, gi) => {
    const rows = g.files.map((f, fi) => `<tr>
      <td><input type="checkbox" ${dupeSel.has(f.path)?"checked":""}
        onclick="dupeToggle('${esc(f.path).replace(/'/g,"\\'")}', this.checked)"></td>
      <td class="nm" title="${esc(f.path)}" style="max-width:520px">${fi===0?"⭐ ":""}${esc(f.path.replace(/^C:\/Users\/[^/]+\//,"~/"))}</td>
      <td>${esc(f.mtime)}</td></tr>`).join("");
    return `<div style="border:1px solid var(--border);border-radius:10px;padding:10px 12px;margin-top:10px">
      <b>${fmt(g.size)}</b> × ${g.files.length} 份 · 可省 ${fmt(g.wasted)}
      <table class="exp-table" style="margin-top:4px">${rows}</table></div>`;
  }).join("");
  modal.innerHTML = `<h3>🔁 重复文件查找</h3>
    <div class="hint">${d.groups.length} 组重复 · 合计可省 <b>${fmt(d.total_wasted)}</b> · ${esc(d.note)}${d.truncated?" ·（超时截断）":""}</div>
    ${cards}
    <div class="foot" style="justify-content:space-between">
      <button class="btn small ghost" onclick="dupeAutoPick()">每组保留 ⭐ 第一份，勾选其余</button>
      <span style="display:flex;gap:10px">
        <span id="dupefoot" class="hint"></span>
        <button class="btn small danger" id="dupedelbtn" style="display:none" onclick="dupeDelete()">移入隔离区</button>
        <button class="btn small ghost" onclick="closeModal()">关闭</button>
      </span></div>`;
  renderDupeFoot();
}
function dupeToggle(p, on) { on ? dupeSel.add(p) : dupeSel.delete(p); renderDupeFoot(); }
function dupeAutoPick() {
  dupeSel = new Set();
  for (const g of dupeData.groups) g.files.slice(1).forEach(f => dupeSel.add(f.path));
  renderDupes();
}
function renderDupeFoot() {
  const foot = document.getElementById("dupefoot"), btn = document.getElementById("dupedelbtn");
  if (!foot || !btn) return;
  let total = 0;
  for (const g of (dupeData.groups||[])) for (const f of g.files) if (dupeSel.has(f.path)) total += g.size;
  foot.textContent = dupeSel.size ? `已选 ${dupeSel.size} 个文件 · ${fmt(total)}` : "";
  btn.style.display = dupeSel.size ? "" : "none";
}
async function dupeDelete() {
  const paths = [...dupeSel];
  for (const g of dupeData.groups) {   // 防呆：不允许把某组的全部副本都删光
    if (g.files.every(f => dupeSel.has(f.path))) {
      alert(`有一组重复文件被全选了（${g.files[0].path}…）——每组至少要留一份！已取消操作。`); return;
    }
  }
  if (!confirm(`将把 ${paths.length} 个重复副本移入隔离区（每组保留未勾选的副本）。确定？`)) return;
  const res = await api("/api/clean_paths", {paths});
  const bad = res.results.filter(r => r.status !== "完成");
  alert(`完成 ${res.results.length - bad.length} 项，移入隔离区 ${fmt(res.total_bytes)}。` +
    (bad.length ? `\n未处理 ${bad.length} 项：\n` + bad.map(r => `· ${r.path}：${r.note||r.status}`).join("\n") : ""));
  dupeData = null; dupeSel = new Set();
  refreshQuarantine(); openDupes();
}

/* ---------- 卸载残留检测（BCU 思路） ---------- */
let leftData = null, leftSel = new Set();
async function openLeftovers() {
  const modal = document.getElementById("modal");
  modal.classList.add("wide");
  modal.innerHTML = `<h3>🧩 卸载残留检测</h3><div style="padding:22px;text-align:center">
    <span class="spin"></span><div class="hint" style="margin-top:8px">正在比对注册表已装程序清单与 Program Files 实际目录…</div></div>`;
  openModal();
  if (!leftData) {
    try { leftData = await api("/api/leftovers", {}); }
    catch (e) { leftData = {error: String(e)}; }
  }
  renderLeftovers();
}
function renderLeftovers() {
  const modal = document.getElementById("modal");
  const d = leftData;
  if (d.error) { modal.innerHTML = `<h3>🧩 卸载残留检测</h3><div class="notice bad">${esc(d.error)}</div>
    <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`; return; }
  if (!d.items.length) {
    modal.innerHTML = `<h3>🧩 卸载残留检测</h3><div class="notice">✅ 未发现疑似卸载残留（已装程序 ${d.installed_count} 个，全部对得上号）。</div>
      <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`; return;
  }
  const rows = d.items.map(it => `<tr>
    <td><input type="checkbox" ${leftSel.has(it.path)?"checked":""}
      onclick="leftToggle('${esc(it.path).replace(/'/g,"\\'")}', this.checked)"></td>
    <td class="nm" title="${esc(it.path)}">📁 ${esc(it.path)}</td>
    <td class="num">${fmt(it.size)}${it.size_exact?"":"≈"}</td>
    <td>${esc(it.mtime)}</td></tr>`).join("");
  modal.innerHTML = `<h3>🧩 卸载残留检测</h3>
    <div class="notice bad">⚠ ${esc(d.note)}</div>
    <div style="overflow-x:auto"><table class="exp-table" style="margin-top:8px">
      <tr style="color:var(--muted);font-size:12px"><td></td><td>目录（注册表里找不到对应程序）</td><td>大小</td><td>最后修改</td></tr>
      ${rows}</table></div>
    <div class="foot">
      <span id="leftfoot" class="hint"></span>
      <button class="btn small danger" id="leftdelbtn" style="display:none" onclick="leftDelete()">移入隔离区</button>
      <button class="btn small ghost" onclick="closeModal()">关闭</button></div>`;
  renderLeftFoot();
}
function leftToggle(p, on) { on ? leftSel.add(p) : leftSel.delete(p); renderLeftFoot(); }
function renderLeftFoot() {
  const foot = document.getElementById("leftfoot"), btn = document.getElementById("leftdelbtn");
  if (!foot || !btn) return;
  const total = (leftData.items||[]).filter(i => leftSel.has(i.path)).reduce((a,i) => a + i.size, 0);
  foot.textContent = leftSel.size ? `已选 ${leftSel.size} 项 · ${fmt(total)}` : "";
  btn.style.display = leftSel.size ? "" : "none";
}
async function leftDelete() {
  const paths = [...leftSel];
  if (!confirm(`确认这些软件都已卸载？将把 ${paths.length} 个目录移入隔离区（可反悔）。`)) return;
  const res = await api("/api/clean_paths", {paths});
  const bad = res.results.filter(r => r.status !== "完成");
  alert(`完成 ${res.results.length - bad.length} 项，移入隔离区 ${fmt(res.total_bytes)}。` +
    (bad.length ? `\n未处理 ${bad.length} 项：\n` + bad.map(r => `· ${r.path}：${r.note||r.status}`).join("\n") : ""));
  leftData = null; leftSel = new Set();
  refreshQuarantine(); openLeftovers();
}

/* 已清理状态：本次扫描之后清理过的项，标记 ✓ */
const cleanedMap = {};
async function loadCleanlog() {
  try {
    const d = await (await fetch("/api/cleanlog")).json();
    const scanTs = new Date(m.scanned_at.replace(" ", "T"));
    for (const e of (d.entries || []))
      if (new Date(e.ts.replace(" ", "T")) > scanTs)
        cleanedMap[e.path.toLowerCase()] = e;
    if (Object.keys(cleanedMap).length) renderRows();
  } catch (e) {}
}
async function rescan() {
  const modal = document.getElementById("modal");
  modal.innerHTML = `<h3>重新扫描中…</h3><div style="padding:24px;text-align:center"><span class="spin"></span>
    <div class="hint" style="margin-top:10px">正在重新扫描磁盘并生成新报告（约 20~60 秒），完成后页面会自动刷新</div></div>`;
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

async function refreshQuarantine() {
  try {
    const q = await api("/api/quarantine", {action: "status"});
    const pill = document.getElementById("qpill");
    if (q.total_bytes > 0) {
      pill.style.display = "";
      pill.innerHTML = `🗑️ 隔离区 ${fmt(q.total_bytes)} <a style="color:var(--accent);cursor:pointer;margin-left:4px" onclick="emptyQuarantine()">复检并清空</a>`;
    } else pill.style.display = "none";
  } catch (e) {}
}

/* 清空前复检：逐文件扫描隔离区，标出不可再生特征，按批次操作，可整批还原 */
async function emptyQuarantine() {
  const modal = document.getElementById("modal");
  modal.classList.add("wide");
  modal.innerHTML = `<h3>🗑️ 隔离区复检</h3><div style="padding:22px;text-align:center">
    <span class="spin"></span><div class="hint" style="margin-top:8px">正在逐个文件复检隔离区内容…</div></div>`;
  openModal();
  let d;
  try { d = await api("/api/quarantine_review", {}); }
  catch (e) { modal.innerHTML = `<h3>复检失败</h3><div class="notice bad">${esc(String(e))}</div>
    <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`; return; }
  if (!d.batches || !d.batches.length) {
    modal.innerHTML = `<h3>🗑️ 隔离区复检</h3><div class="notice">隔离区是空的。</div>
      <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`;
    refreshQuarantine(); return;
  }
  const anySus = d.batches.some(b => b.suspicious.length);
  const cards = d.batches.map(b => {
    const date = `${b.batch.slice(0,4)}-${b.batch.slice(4,6)}-${b.batch.slice(6,8)} ${b.batch.slice(9,11)}:${b.batch.slice(11,13)}`;
    const sus = b.suspicious.length
      ? `<div class="notice bad" style="margin-top:8px">⚠️ 复检发现 ${b.suspicious.length} 个不可再生特征文件——清空前先确认：</div>` +
        `<table class="exp-table" style="margin-top:4px">` +
        b.suspicious.slice(0,10).map(s =>
          `<tr><td class="nm" title="${esc(s.file)}">📄 ${esc(s.file.split("\\").pop())}</td>
           <td class="num">${fmt(s.size)}</td><td class="why">${esc(s.reason)}</td></tr>`).join("") +
        `</table>` + (b.suspicious.length > 10 ? `<div class="hint">…等 ${b.suspicious.length} 个</div>` : "")
      : `<div class="hint" style="margin-top:6px">✅ 复检通过：${b.file_count.toLocaleString()} 个文件均为可再生类型（缓存/日志/临时文件特征）</div>`;
    const src = b.sources.length
      ? `<div class="hint">来源：${b.sources.map(s => esc(s)).join("、")}</div>` : "";
    return `<div style="border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin-top:10px">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <b>批次 ${date}</b>
        <span class="hint">${b.file_count.toLocaleString()} 个文件 · ${fmt(b.total_bytes)}</span>
        <span style="flex:1"></span>
        ${b.has_manifest ? `<button class="btn small ghost" onclick="restoreBatch('${b.batch}')">↩ 还原此批次</button>` : `<span class="hint">（无清单，只能手动还原）</span>`}
        <button class="btn small danger" onclick="emptyBatch('${b.batch}')">清空此批次</button>
      </div>${src}${sus}</div>`;
  }).join("");
  modal.innerHTML = `<h3>🗑️ 隔离区复检</h3>
    <div class="hint">清空 = 永久删除，不可恢复。还原 = 按清单放回原位置。</div>
    ${cards}
    <div class="foot">
      <button class="btn ghost" onclick="closeModal()">先不动</button>
      <button class="btn danger" onclick="emptyBatch(null)">${anySus ? "⚠️ 仍要清空全部" : "清空全部批次"}</button>
    </div>`;
}
async function emptyBatch(batch) {
  const what = batch ? `批次 ${batch}` : "全部批次";
  if (!confirm(`将永久删除隔离区${what}（不可恢复）。确定？`)) return;
  const r = await api("/api/quarantine", {action: "empty", batch});
  alert("已清空，释放 " + fmt(r.freed_bytes || 0));
  refreshQuarantine();
  emptyQuarantine();   // 刷新复检视图
}
async function restoreBatch(batch) {
  if (!confirm(`将把批次 ${batch} 的所有文件按清单放回原位置。确定？`)) return;
  const r = await api("/api/quarantine_restore", {batch});
  let msg = `已还原 ${r.restored} 项（${fmt(r.restored_bytes||0)}）。`;
  if (r.skipped_exists && r.skipped_exists.length)
    msg += `\n${r.skipped_exists.length} 项因原位置已有同名文件而保留在隔离区。`;
  if (r.failed && r.failed.length) msg += `\n失败 ${r.failed.length} 项。`;
  alert(msg);
  refreshQuarantine();
  emptyQuarantine();
}

/* ---------- treemap（与 v1.0 相同的 squarify，微调样式） ---------- */
function nodeSafety(node, path) {
  const ai = aiMap[path.toLowerCase()];
  if (node && node.rule) return node.rule.safety;
  if (ai) return ai.safety;
  return "none";
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
let navStack = [];
function renderTreemap() {
  const cur = navStack[navStack.length-1];
  const el = document.getElementById("treemap");
  el.innerHTML = "";
  const W = el.clientWidth, H = el.clientHeight;
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
    const div = document.createElement("div");
    div.className = "block";
    div.tabIndex = 0;
    div.style.cssText = `left:${r.x+GAP/2}px; top:${r.y+GAP/2}px; width:${Math.max(0,r.w-GAP)}px; height:${Math.max(0,r.h-GAP)}px;` +
      `background:color-mix(in srgb, ${s.bg} 30%, var(--surface));`;
    if (r.w > 55 && r.h > 26)
      div.innerHTML = `<div class="lb">${s.icon} ${esc(it.name)}<span class="sz">${fmt(it.size)}</span></div>`;
    div.onmousemove = e => showTip(e, it, safety);
    div.onmouseleave = hideTip;
    div.onclick = e => { e.stopPropagation(); hideTip();
      showDetail(it, safety);
      if (it.node && Object.keys(it.node.dirs||{}).length) {
        navStack.push({name: it.name, node: it.node, path: it.path});
        renderTreemap();
      }
    };
    el.appendChild(div);
  }
  document.getElementById("crumbs").innerHTML = navStack.map((n,i) =>
    i === navStack.length-1 ? `<b>${esc(n.name)}</b>`
    : `<a onclick="jump(${i})">${esc(n.name)}</a>`).join(" › ");
}
function jump(i) { navStack = navStack.slice(0, i+1); renderTreemap(); }
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
function showDetail(it, safety) {
  const s = S[safety];
  const rule = it.node && it.node.rule;
  const ai = aiMap[it.path.toLowerCase()];
  const title = (rule && rule.title) || (ai && ai.title) || it.name;
  const desc = (rule && rule.desc) || (ai && ai.desc) ||
    (it.pseudo ? "页面文件、系统还原点、商店应用等需要管理员权限才能读取的区域。"
               : "知识库暂未收录。在下方清单里点开对应行，可实时深挖并让 AI 分析。");
  const act = (rule && rule.action) || (ai && ai.action) || "";
  document.getElementById("detail").innerHTML =
    `<h3>${esc(title)}${ai && !rule ? '<span class="aitag">AI 分析</span>' : ""}</h3>` +
    `<div class="path">${esc(it.path)}</div>` +
    `<div class="size">${fmt(it.size)}</div>` +
    `<div><span class="badge" style="color:${s.color}">${s.icon} ${s.label}</span></div>` +
    `<div class="desc">${esc(desc)}</div>` +
    (act ? `<div class="act"><b>清理方法：</b>${esc(act)}</div>` : "") +
    (!it.pseudo && !it.isFile ? `<div style="margin-top:10px"><button class="btn small ghost" ${SERVER?"":"disabled"}
      onclick="openExplorer('${esc(it.path)}')">📂 逐项浏览判定</button></div>` : "");
}

/* ---------- 决策清单 ---------- */
const rows = [];
{
  const seen = new Set();
  for (const f of DATA.findings) { rows.push({...f, src: "kb"}); seen.add(f.path.toLowerCase()); }
  for (const n of AI_NOTES.notes) if (!seen.has(n.path.toLowerCase())) {
    const size = (DATA.unknowns.find(u => u.path.toLowerCase() === n.path.toLowerCase()) || {}).size || n.size || 0;
    if (size < 50*1024*1024) continue;   // 已清理/已不存在的历史分析条目，不再显示
    rows.push({ path: n.path, size, title: n.title, safety: n.safety, desc: n.desc, action: n.action, src: "ai" });
  }
}
let filter = "all";
let sortKey = "size", sortDir = -1;      // -1 = 降序
const expanded = new Set();
const checked = new Set();
const detailCache = {};

const FILTERS = [["all","全部"],["safe","✅ 可放心清理"],["caution","⚠️ 需注意方法"],
  ["user","👤 个人文件"],["danger","🚫 别手动删"],["keep","🔒 保留勿删"],["ai","🤖 AI 分析项"]];
document.getElementById("filters").innerHTML = FILTERS.map(([k,l]) =>
  `<button class="fbtn${k==="all"?" on":""}" data-f="${k}" onclick="setFilter('${k}',this)">${l}</button>`).join("");
function setFilter(k, btn) {
  filter = k;
  document.querySelectorAll(".fbtn").forEach(b => b.classList.toggle("on", b === btn));
  renderRows();
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
  // 表头箭头
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
    const tr = document.createElement("tr");
    tr.className = "frow" + (expanded.has(r.path) ? " open" : "");
    if (cl) tr.style.opacity = ".55";
    tr.innerHTML =
      `<td>${canCheck ? `<input type="checkbox" ${checked.has(r.path)?"checked":""}>` : ""}</td>` +
      `<td class="num">${cl ? `<s>${fmt(r.size)}</s>` : fmt(r.size)}</td>` +
      `<td style="white-space:nowrap">${cl
        ? `<span class="badge" style="color:var(--safe)">✓ 已清理 ${fmt(cl.bytes)}</span>`
        : `<span class="badge" style="color:${s.color}">${s.icon} ${s.label}</span>`}</td>` +
      `<td><div class="t"><span class="caret">▶</span>${esc(r.title)}${r.src==="ai"?'<span class="aitag">AI 分析</span>':""}</div>` +
      `<div class="p">${esc(r.path)}</div>` +
      `<div class="d">${esc(r.desc)}</div>` +
      (r.action ? `<div class="a"><b>清理方法：</b>${esc(r.action)}</div>` : "") + `</td>`;
    const cb = tr.querySelector("input");
    if (cb) cb.onclick = e => { e.stopPropagation();
      cb.checked ? checked.add(r.path) : checked.delete(r.path); updateBar(); };
    tr.onclick = () => toggleDrawer(r);
    tb.appendChild(tr);
    if (expanded.has(r.path)) tb.appendChild(buildDrawer(r));
  }
  updateBar();
}
function toggleDrawer(r) {
  expanded.has(r.path) ? expanded.delete(r.path) : expanded.add(r.path);
  renderRows();
  if (expanded.has(r.path) && SERVER && !detailCache[r.path]) fetchDetail(r);
}
function findNode(path) {
  // path 形如 "C:/Users/xx"，DATA.tree 是 C: 的根
  const parts = path.split("/").slice(1);
  let node = DATA.tree;
  for (const p of parts) {
    node = (node.dirs || {})[p];
    if (!node) return null;
  }
  return node;
}
function buildDrawer(r) {
  const tr = document.createElement("tr");
  tr.className = "drawer";
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
      (sub ? `<table class="mini">${sub}</table>` : `<div class="hint">此目录无 50MB 以上的子项，或未在扫描树中。</div>`) +
      `<div style="margin-top:8px"><button class="btn small ghost" ${SERVER?"":"disabled"}
        onclick="event.stopPropagation();openExplorer('${esc(r.path)}')">📂 逐项浏览判定</button>
        <span class="hint" style="margin-left:6px">逐个文件/子目录判定能不能删</span></div>` +
    `</div>` +
    `<div><h4>实时深挖 ${SERVER ? "" : "（需启动服务）"}</h4><div class="live">` +
      (cached ? liveHtml(cached) : (SERVER ? `<span class="spin"></span> 正在读取目录内容…` :
        `<div class="hint">用 <code>python serve.py</code> 打开报告后，这里会实时列出最大文件、类型分布和最近使用时间。</div>`)) +
    `</div></div>` +
    `<div class="aibox" style="margin-top:14px">` + (r.aiText
      ? `<b>🤖 AI 深度分析</b>\n${esc(r.aiText)}`
      : `<button class="btn small ghost" ${SERVER?"":"disabled"} onclick="event.stopPropagation();askAI('${esc(r.path)}')">🤖 生成 AI 深度分析</button>` +
        `<span class="hint" style="margin-left:8px">调用本机 Claude 分析这个目录到底是什么、能不能删（约 10~30 秒）</span>`) +
    `</div></td>`;
  tr.onclick = e => e.stopPropagation();
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
async function askAI(path) {
  const r = rows.find(x => x.path === path);
  if (!r) return;
  const box = document.querySelector(`tr.drawer[data-path="${CSS.escape(path)}"] .aibox`);
  if (box) box.innerHTML = `<span class="spin"></span> Claude 正在分析这个目录…（10~30 秒）`;
  try {
    const res = await api("/api/ai", {path, context: {title: r.title, safety: r.safety, desc: r.desc, size: r.size}});
    r.aiText = res.text || res.error || "（无结果）";
  } catch (e) { r.aiText = "AI 分析失败: " + e; }
  renderRows();
}

/* ---------- 提交清理 ---------- */
function updateBar() {
  const sel = rows.filter(r => checked.has(r.path));
  const bar = document.getElementById("actionbar");
  bar.classList.toggle("show", sel.length > 0);
  const total = sel.reduce((a,r) => a + r.size, 0);
  document.getElementById("absum").innerHTML =
    `已选 <b>${sel.length}</b> 项 · 涉及 <b>${fmt(total)}</b>`;
  document.getElementById("submitbtn").textContent = SERVER ? "提交清理" : "生成清理计划";
}
function clearSel() { checked.clear(); renderRows(); }

let pendingClean = [];
async function submitClean() {
  const sel = rows.filter(r => checked.has(r.path));
  if (!sel.length) return;
  const autos = sel.filter(r => r.safety === "safe");
  const manuals = sel.filter(r => r.safety !== "safe");
  const modal = document.getElementById("modal");
  if (!SERVER) {   // 静态模式：只出计划文本
    let txt = "===== C 盘清理计划 =====\n\n";
    for (const r of sel) {
      const s = S[r.safety] || S.none;
      txt += `[${s.icon} ${s.label}] ${r.path} (${fmt(r.size)})\n  ${r.title}\n  方法: ${r.action || "见报告"}\n\n`;
    }
    modal.innerHTML = `<h3>清理计划（只读模式）</h3>
      <textarea style="width:100%;height:260px;background:var(--sunken);color:var(--ink);border:1px solid var(--border);border-radius:8px;padding:10px;font:12px/1.5 Consolas,monospace" onclick="this.select()">${esc(txt)}</textarea>
      <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`;
    openModal(); return;
  }
  // 占用预检：有程序正从目录里运行的项，本轮自动排除
  modal.innerHTML = `<h3>安全检查</h3><div style="padding:20px;text-align:center"><span class="spin"></span>
    <div class="hint" style="margin-top:10px">正在检查是否有程序正在这些目录里运行…</div></div>`;
  openModal();
  const occ = {};
  try {
    const pre = await api("/api/precheck", {paths: autos.map(r => r.path)});
    for (const p of pre.results) if (p.occupied) occ[p.path] = p;
  } catch (e) {}
  const ready = autos.filter(r => !occ[r.path]);
  const blocked = autos.filter(r => occ[r.path]);
  pendingClean = ready;
  modal.innerHTML = `<h3>确认清理</h3>` +
    (ready.length ? `<div class="notice">🤖 <b>将自动清理 ${ready.length} 项</b>（均为 ✅ 级且无程序占用），
      默认先移入<b>隔离区</b>——不满意随时可还原，确认没问题后再"清空隔离区"真正释放空间。</div>` +
      ready.map(r => `<div class="mrow"><span class="ok">✔ 无占用</span> <b>${esc(r.title)}</b> · ${fmt(r.size)}<div class="p2">${esc(r.path)}</div></div>`).join("") : "") +
    (blocked.length ? `<div class="notice" style="margin-top:10px">⛔ <b>${blocked.length} 项检测到程序正在其中运行，本轮已自动排除</b>（防止出现"删了缓存、程序崩了"的情况）：</div>` +
      blocked.map(r => `<div class="mrow"><span class="bad">⚠ 占用中</span> <b>${esc(r.title)}</b> · ${fmt(r.size)}
        <div class="p2">${esc(r.path)}</div>
        <div>正在运行：${esc(occ[r.path].procs.map(x => x.name).join("、"))}（共 ${occ[r.path].proc_count} 个进程）——关闭相关软件后重新提交即可</div></div>`).join("") : "") +
    (manuals.length ? `<div class="notice" style="margin-top:10px">✋ <b>${manuals.length} 项需要按方法手动处理</b>（工具不代劳，防止误删）：</div>` +
      manuals.map(r => `<div class="mrow"><b>${esc(r.title)}</b> · ${fmt(r.size)}<div class="p2">${esc(r.path)}</div><div>方法：${esc(r.action||"")}</div></div>`).join("") : "") +
    `<label style="display:flex;gap:8px;align-items:center;margin-top:14px;font-size:13px">
       <input type="checkbox" id="permcb"> 跳过隔离区，直接永久删除（快，但不可反悔）</label>
    <div class="foot">
      <button class="btn ghost" onclick="closeModal()">再想想</button>
      ${ready.length ? `<button class="btn" onclick="doClean()">开始清理 ${ready.length} 项</button>` : ""}
    </div>`;
}
async function doClean() {
  const autos = pendingClean;
  const permanent = document.getElementById("permcb").checked;
  const modal = document.getElementById("modal");
  modal.innerHTML = `<h3>清理中…</h3><div style="padding:24px;text-align:center"><span class="spin"></span>
    <div class="hint" style="margin-top:10px">正在${permanent?"删除":"移入隔离区"}，大目录可能需要一两分钟</div></div>`;
  let res;
  try { res = await api("/api/clean", {paths: autos.map(r => r.path), permanent}); }
  catch (e) { modal.innerHTML = `<h3>出错了</h3><div class="notice bad">${esc(String(e))}</div>
    <div class="foot"><button class="btn ghost" onclick="closeModal()">关闭</button></div>`; return; }
  // 立刻在清单里标记"已清理"，无需等重新扫描
  for (const r of res.results) if (r.status === "完成")
    cleanedMap[r.path.toLowerCase()] = { bytes: r.bytes || 0 };
  modal.innerHTML = `<h3>清理完成</h3>
    <div class="notice">${esc(res.note)}</div>` +
    res.results.map(r => `<div class="mrow">
      <span class="${r.status==="完成"?"ok":"bad"}">${r.status==="完成"?"✔":"✖"} ${esc(r.status)}</span>
      <b>${esc(r.path)}</b>` +
      (r.status==="完成" ? ` · 处理 ${fmt(r.bytes||0)}${r.skipped_inuse?`（${r.skipped_inuse} 个文件被占用已跳过）`:""}` :
        `<div class="p2">${esc(r.note||"")}</div>`) + `</div>`).join("") +
    `<div style="margin-top:10px;font-size:15px">合计处理 <b>${fmt(res.total_bytes)}</b></div>
    <div class="foot">
      ${!res.permanent && res.total_bytes > 0 ? `<button class="btn danger" onclick="closeModal();emptyQuarantine()">立即清空隔离区释放空间</button>` : ""}
      <button class="btn ghost" onclick="rescan()">🔄 重新扫描更新报告</button>
      <button class="btn ghost" onclick="closeModal();refreshQuarantine()">完成</button>
    </div>`;
  clearSel();
}
/* ---------- 逐项浏览判定（文件浏览器） ---------- */
let expStack = [];
const browseCache = {};
const aiVerdicts = {};   // path -> {name: {safety, why}}
let expSel = new Set(), expSelPath = null;   // 当前目录中勾选的条目名
const safeScanCache = {};                    // root -> /api/safe_scan 结果
let safeSel = new Set();                     // 安全汇总列表中勾选的完整路径
function openExplorer(path) { expStack = [path]; renderExplorer(); }
function expJump(i) { expStack = expStack.slice(0, i+1); renderExplorer(); }
function expEnter(name) { expStack.push(expStack[expStack.length-1] + "/" + name); renderExplorer(); }
function expToggle(name, on) { on ? expSel.add(name) : expSel.delete(name); renderExpFoot(); }

async function renderExplorer() {
  const path = expStack[expStack.length-1];
  const modal = document.getElementById("modal");
  modal.classList.add("wide");
  const crumbs = expStack.map((p,i) => {
    const label = i === 0 ? p : p.split("/").pop();
    return i === expStack.length-1 ? `<b>${esc(label)}</b>` : `<a onclick="expJump(${i})">${esc(label)}</a>`;
  }).join(" › ");
  modal.innerHTML = `<h3>📂 逐项浏览判定</h3><div class="exp-crumbs">${crumbs}</div>
    <div style="padding:22px;text-align:center"><span class="spin"></span>
    <div class="hint" style="margin-top:8px">正在读取并判定每一项…（大目录最多几秒）</div></div>`;
  openModal();
  let d = browseCache[path];
  if (!d) {
    try { d = await api("/api/browse", {path}); browseCache[path] = d; }
    catch (e) { d = {error: String(e)}; }
  }
  if (d.error) {
    modal.innerHTML = `<h3>📂 逐项浏览判定</h3><div class="exp-crumbs">${crumbs}</div>
      <div class="notice bad">${esc(d.error)}</div>
      <div class="foot"><button class="btn ghost" onclick="closeExplorer()">关闭</button></div>`;
    return;
  }
  if (expSelPath !== path) { expSel = new Set(); expSelPath = path; }
  const av = aiVerdicts[path] || {};
  const unknownCount = d.entries.filter(e => !e.safety && !av[e.name]).length;
  const rowsHtml = d.entries.map(e => {
    const v = av[e.name];
    const safety = e.safety || (v && v.safety) || "none";
    const why = e.why || (v && v.why) ||
      (safety === "none" ? "未识别——点下方'AI 判定未识别项'" : "");
    const s = S[safety] || S.none;
    const fromAI = !e.safety && v;
    const canDel = safety !== "keep" && safety !== "danger";
    const nm = esc(e.name).replace(/'/g, "\\'");
    return `<tr>
      <td>${canDel ? `<input type="checkbox" ${expSel.has(e.name)?"checked":""}
        onclick="expToggle('${nm}', this.checked)">` : ""}</td>
      <td class="nm">${e.is_dir ? `<a onclick="expEnter('${nm}')">📁 ${esc(e.name)}</a>` : `📄 ${esc(e.name)}`}</td>
      <td class="num">${fmt(e.size)}${e.size_exact ? "" : "≈"}</td>
      <td>${esc(e.mtime)}</td>
      <td style="white-space:nowrap"><span class="badge" style="color:${s.color}">${s.icon} ${s.label}</span>${fromAI ? '<span class="aitag">AI</span>' : ""}</td>
      <td class="why">${esc(why)}</td></tr>`;
  }).join("");
  const isRoot = expStack.length === 1;
  modal.innerHTML = `<h3>📂 逐项浏览判定</h3><div class="exp-crumbs">${crumbs}</div>` +
    (isRoot ? `<div id="safescan"></div>` : "") +
    `<div style="overflow-x:auto"><table class="exp-table">
      <tr style="color:var(--muted);font-size:12px"><td></td><td>名称（点📁进入）</td><td>大小</td><td>修改日期</td><td>判定</td><td>理由 / 建议</td></tr>
      ${rowsHtml}</table></div>
    <div class="foot" style="justify-content:space-between;align-items:center">
      <span class="hint">${d.entries.length} 项${unknownCount ? ` · ${unknownCount} 项未识别` : ""} · "≈"为估算 · 🔒/🚫级不可勾选</span>
      <span style="display:flex;gap:10px;align-items:center">
        <span id="expfoot" class="hint"></span>
        <button class="btn small danger" id="expdelbtn" style="display:none" onclick="expDelete()">删除选中项</button>
        ${unknownCount ? `<button class="btn small" onclick="aiJudge()">🤖 AI 判定未识别项（${unknownCount}）</button>` : ""}
        ${expStack.length > 1 ? `<button class="btn small ghost" onclick="expJump(${expStack.length-2})">⬅ 返回上级</button>` : ""}
        <button class="btn small ghost" onclick="closeExplorer()">关闭</button>
      </span></div>`;
  renderExpFoot();
  if (isRoot) loadSafeScan(path);
}

/* 安全可删汇总：进入逐项判定时自动递归收集所有 ✅safe 项 */
async function loadSafeScan(root) {
  const box = document.getElementById("safescan");
  if (!box) return;
  if (!safeScanCache[root]) {
    box.innerHTML = `<div class="notice" style="margin-bottom:12px"><span class="spin"></span>
      正在递归汇总此目录下所有「✅ 可放心清理」的项目…</div>`;
    try { safeScanCache[root] = await api("/api/safe_scan", {path: root}); }
    catch (e) { safeScanCache[root] = {error: String(e)}; }
  }
  renderSafeScan(root);
}
function renderSafeScan(root) {
  const box = document.getElementById("safescan");
  const d = safeScanCache[root];
  if (!box || !d) return;
  if (d.error) { box.innerHTML = `<div class="notice bad" style="margin-bottom:12px">${esc(d.error)}</div>`; return; }
  if (!d.items.length) {
    box.innerHTML = `<div class="notice" style="margin-bottom:12px">✅ 此目录下没有扫到可直接安全删除的项目。</div>`;
    return;
  }
  const rows = d.items.map(it => `<tr>
    <td><input type="checkbox" ${safeSel.has(it.path)?"checked":""}
      onclick="safeToggle('${esc(it.path).replace(/'/g,"\\'")}', this.checked)"></td>
    <td class="nm" title="${esc(it.path)}">${it.is_dir?"📁":"📄"} ${esc(it.rel)}</td>
    <td class="num">${fmt(it.size)}${it.size_exact?"":"≈"}</td>
    <td class="why">${esc(it.why||"")}</td></tr>`).join("");
  box.innerHTML = `<div style="border:1px solid var(--border);border-radius:10px;background:var(--sunken);padding:12px 14px;margin-bottom:14px">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">
      <b>✅ 安全可删汇总</b>
      <span class="hint">递归扫出 ${d.items.length} 项 · 合计 ${fmt(d.total)}${d.truncated?" ·（超时截断，仅显示部分）":""}</span>
      <span style="flex:1"></span>
      <label class="hint" style="cursor:pointer"><input type="checkbox" onclick="safeAll(this.checked)"> 全选</label>
      <span id="safefoot" class="hint"></span>
      <button class="btn small danger" id="safedelbtn" style="display:none" onclick="safeDelete()">删除选中</button>
    </div>
    <div style="max-height:260px;overflow-y:auto"><table class="exp-table">${rows}</table></div></div>`;
  renderSafeFoot(root);
}
function safeToggle(p, on) { on ? safeSel.add(p) : safeSel.delete(p); renderSafeFoot(expStack[0]); }
function safeAll(on) {
  const d = safeScanCache[expStack[0]];
  if (!d || !d.items) return;
  safeSel = on ? new Set(d.items.map(i => i.path)) : new Set();
  renderSafeScan(expStack[0]);
}
function renderSafeFoot(root) {
  const d = safeScanCache[root];
  const foot = document.getElementById("safefoot");
  const btn = document.getElementById("safedelbtn");
  if (!d || !d.items || !foot || !btn) return;
  const total = d.items.filter(i => safeSel.has(i.path)).reduce((a,i) => a + i.size, 0);
  foot.textContent = safeSel.size ? `已选 ${safeSel.size} 项 · ${fmt(total)}` : "";
  btn.style.display = safeSel.size ? "" : "none";
}
async function safeDelete() {
  const paths = [...safeSel];
  if (!paths.length) return;
  if (!confirm(`将把 ${paths.length} 项移入隔离区（可反悔）。确定？`)) return;
  const btn = document.getElementById("safedelbtn");
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spin"></span> 处理中…`; }
  let res;
  try { res = await api("/api/clean_paths", {paths}); }
  catch (e) { alert("删除失败: " + e); if (btn) btn.disabled = false; return; }
  const bad = res.results.filter(r => r.status !== "完成");
  let msg = `完成 ${res.results.length - bad.length} 项，移入隔离区 ${fmt(res.total_bytes)}。`;
  if (bad.length) msg += `\n\n未处理 ${bad.length} 项：\n` + bad.map(r => `· ${r.path}：${r.note||r.status}`).join("\n");
  alert(msg);
  safeSel = new Set();
  delete safeScanCache[expStack[0]];
  Object.keys(browseCache).forEach(k => delete browseCache[k]);
  renderExplorer();
  refreshQuarantine();
}
function renderExpFoot() {
  const path = expStack[expStack.length-1];
  const d = browseCache[path];
  const foot = document.getElementById("expfoot");
  const btn = document.getElementById("expdelbtn");
  if (!foot || !btn || !d || !d.entries) return;
  const total = d.entries.filter(e => expSel.has(e.name)).reduce((a,e) => a + e.size, 0);
  foot.textContent = expSel.size ? `已选 ${expSel.size} 项 · ${fmt(total)}` : "";
  btn.style.display = expSel.size ? "" : "none";
  btn.textContent = `删除选中 ${expSel.size} 项`;
}
async function expDelete() {
  const path = expStack[expStack.length-1];
  const names = [...expSel];
  if (!names.length) return;
  if (!confirm(`将把选中的 ${names.length} 项移入隔离区（可反悔，清空隔离区后才真正释放空间）。\n\n` +
               names.slice(0,10).join("\n") + (names.length > 10 ? `\n…等 ${names.length} 项` : "") +
               `\n\n确定？`)) return;
  const btn = document.getElementById("expdelbtn");
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spin"></span> 处理中…`; }
  let res;
  try { res = await api("/api/clean_items", {base: path, names}); }
  catch (e) { alert("删除失败: " + e); if (btn) btn.disabled = false; return; }
  if (res.error) { alert(res.error); if (btn) btn.disabled = false; return; }
  const ok = res.results.filter(r => r.status === "完成");
  const bad = res.results.filter(r => r.status !== "完成");
  let msg = `完成 ${ok.length} 项，移入隔离区 ${fmt(res.total_bytes)}。`;
  if (bad.length) msg += `\n\n未处理 ${bad.length} 项：\n` +
    bad.map(r => `· ${r.name}：${r.note || r.status}`).join("\n");
  alert(msg);
  delete browseCache[path];   // 强制重新读取该目录
  expSel = new Set();
  renderExplorer();
  refreshQuarantine();
}
async function aiJudge() {
  const path = expStack[expStack.length-1];
  const d = browseCache[path];
  if (!d || !d.entries) return;
  const unknown = d.entries.filter(e => !e.safety && !(aiVerdicts[path]||{})[e.name]);
  const modal = document.getElementById("modal");
  const btn = modal.querySelector(".btn.small:not(.ghost)");
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spin"></span> AI 判定中…（10~60 秒）`; }
  try {
    const r = await api("/api/ai_judge", {path, entries: unknown});
    if (r.verdicts) aiVerdicts[path] = Object.assign(aiVerdicts[path] || {}, r.verdicts);
    else alert(r.error || "AI 判定失败");
  } catch (e) { alert("AI 判定失败: " + e); }
  renderExplorer();
}
function closeExplorer() {
  document.getElementById("modal").classList.remove("wide");
  closeModal();
}

function openModal() { document.getElementById("overlay").classList.add("show"); }
function closeModal() { document.getElementById("overlay").classList.remove("show");
  document.getElementById("modal").classList.remove("wide"); }
document.getElementById("overlay").onclick = e => { if (e.target.id === "overlay") closeModal(); };

/* 初始化 */
renderRows();
navStack = [{ name: "C:", node: DATA.tree, path: "C:" }];
renderTreemap();
window.addEventListener("resize", renderTreemap);
</script>
"""


def main():
    in_file = sys.argv[1] if len(sys.argv) > 1 else "output/analysis.json"
    ai_file = sys.argv[2] if len(sys.argv) > 2 else "output/ai_notes.json"
    out_file = sys.argv[3] if len(sys.argv) > 3 else "output/report.html"

    with open(in_file, encoding="utf-8") as f:
        data = json.load(f)
    if os.path.exists(ai_file):
        with open(ai_file, encoding="utf-8") as f:
            ai = json.load(f)
    else:
        ai = {"notes": []}

    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)) \
                   .replace("__AI_NOTES__", json.dumps(ai, ensure_ascii=False))
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("<!doctype html>\n<html lang=\"zh-CN\">\n<body>\n" + html + "\n</body>\n</html>")
    print(f"[report] 报告已生成: {out_file} ({os.path.getsize(out_file)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
