# -*- coding: utf-8 -*-
"""
serve.py — 报告本地服务

让报告页面拥有"真手"：
  GET  /                    报告页面
  GET  /api/ping            探测服务是否在线（页面据此切换交互模式）
  POST /api/detail          按需深挖某个目录：最大文件、文件类型分布、最近修改时间
  POST /api/ai              调用 claude CLI 对某个目录做 AI 深度分析
  POST /api/clean           清理选中项（仅限"✅可放心清理"级；默认移入隔离区，可反悔）
  POST /api/quarantine      查看/清空隔离区

安全设计：
  - 只监听 127.0.0.1
  - /api/clean 只接受 analysis.json 里 safety=="safe" 的路径（白名单），其他一律拒绝
  - 默认移动到同盘隔离区（瞬间完成、可整体撤销），用户确认后才真正删除
"""
import http.server
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import webbrowser

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from knowledge import match_rule, protected_titles  # noqa: E402

OUT = os.path.join(HERE, "output")
PORT = 8756
# 每次启动生成随机令牌，注入报告页面；所有修改类 API 校验它——
# 防止本机其他程序悄悄调用清理接口
TOKEN = secrets.token_hex(16)

DETAIL_TIME_BUDGET = 4.0     # 秒：目录深挖的时间预算
DETAIL_MAX_FILES = 200000


def load_whitelist():
    """可自动清理的路径白名单：analysis.json + ai_notes.json 里 safety=='safe' 的项"""
    wl = {}
    try:
        with open(os.path.join(OUT, "analysis.json"), encoding="utf-8") as f:
            data = json.load(f)
        for it in data.get("findings", []):
            if it.get("safety") == "safe":
                wl[norm(it["path"])] = it
    except OSError:
        pass
    try:
        with open(os.path.join(OUT, "ai_notes.json"), encoding="utf-8") as f:
            ai = json.load(f)
        for it in ai.get("notes", []):
            if it.get("safety") == "safe":
                wl.setdefault(norm(it["path"]), it)
    except OSError:
        pass
    return wl


def norm(p):
    return p.replace("\\", "/").rstrip("/").lower()


def to_win(p):
    return p.replace("/", "\\")


def quarantine_root(target_path):
    """与目标同盘的隔离区（同盘移动瞬间完成）；建不了就退回 LOCALAPPDATA。"""
    drive = os.path.splitdrive(to_win(target_path))[0] or "C:"
    for base in (drive + "\\.c-cleaner-quarantine",
                 os.path.join(os.environ.get("LOCALAPPDATA", drive + "\\"), "c-cleaner", "quarantine")):
        try:
            os.makedirs(base, exist_ok=True)
            return base
        except OSError:
            continue
    return None


def dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                total += os.stat(os.path.join(root, f), follow_symlinks=False).st_size
            except OSError:
                pass
    return total


# ---------- 逐文件判定引擎 ----------
EXT_RULES = {
    ".log": ("safe", "日志文件，仅用于排查问题，可删"),
    ".tmp": ("safe", "临时文件，可删"),
    ".temp": ("safe", "临时文件，可删"),
    ".dmp": ("safe", "崩溃转储快照，不排查故障就没用，可删"),
    ".etl": ("safe", "Windows 跟踪日志，可删"),
    ".cache": ("safe", "缓存文件，删后自动重建"),
    ".bak": ("caution", "备份文件——确认原文件完好后可删"),
    ".old": ("caution", "旧版本备份——确认新版正常后可删"),
    ".chk": ("safe", "磁盘检查恢复的碎片，基本无用"),
    ".pdb": ("caution", "调试符号文件，不做开发调试可删"),
    ".msi": ("caution", "安装包——软件装完后安装包可删（但在 C:\\Windows\\Installer 里的绝不能删）"),
    ".msp": ("caution", "补丁包——同上，Windows\\Installer 里的勿动"),
    ".exe": ("user", "可执行程序——若是下载的安装包且已装完可删；若是软件本体勿删"),
    ".zip": ("user", "压缩包——确认内容已解压或不再需要后可删"),
    ".7z": ("user", "压缩包——同上"),
    ".rar": ("user", "压缩包——同上"),
    ".iso": ("user", "光盘镜像，通常很大——用完可删或移 D 盘"),
    ".mp4": ("user", "视频文件——自行决定，可移 D 盘"),
    ".mov": ("user", "视频文件——同上"),
    ".mkv": ("user", "视频文件——同上"),
    ".psd": ("user", "Photoshop 源文件——你的作品，勿随意删"),
    ".dll": ("keep", "程序组件——缺了对应软件会坏，勿单独删"),
    ".sys": ("keep", "系统/驱动文件，勿删"),
}
DIR_HINTS = [
    (("cache", "caches", "cached", "gpucache", "shadercache", "code cache", "dawncache"),
     "safe", "缓存目录，删后程序会自动重建（首次会慢一点）"),
    (("temp", "tmp"), "safe", "临时目录，可清空"),
    (("logs", "log", "crashdumps", "crash reports", "crashpad", "minidump", "dumps"),
     "safe", "日志/崩溃报告目录，仅用于排查问题"),
    (("downloadcache", "download cache", "installer cache", "package cache"),
     "caution", "下载/安装包缓存——装完就没用，但先确认对应软件不再需要修复"),
    (("node_modules",), "caution", "项目依赖目录——项目还在用就别删；不用了可删，重装跑 npm install"),
    (("backup", "backups", "bak", "old"), "caution", "备份目录——确认不需要回滚后可删"),
    (("updates", "update", "pending"), "caution", "更新包暂存——更新完成后可删"),
]


def load_ai_notes_map():
    try:
        with open(os.path.join(OUT, "ai_notes.json"), encoding="utf-8") as f:
            return {norm(n["path"]): n for n in json.load(f).get("notes", [])}
    except (OSError, json.JSONDecodeError):
        return {}


def judge_entry(drive_rel, name, is_dir, ai_notes):
    """单个文件/目录的判定，优先级：
    ① 知识库/AI笔记 精确命中该条目 ② 目录名/扩展名启发式 ③ 祖先目录规则兜底。
    返回 (safety, why) 或 (None, None) 表示未识别。"""
    full = norm("C:/" + drive_rel)
    rule = match_rule(drive_rel)
    if rule is not None:
        return rule["safety"], rule["title"] + "。" + rule["action"]
    if full in ai_notes:
        n = ai_notes[full]
        return n["safety"], n["title"] + "。" + n["action"]

    low = name.lower()
    if is_dir:
        for keys, safety, why in DIR_HINTS:
            if low in keys or any(low.startswith(k) for k in keys if len(k) > 4):
                return safety, why
    else:
        ext = os.path.splitext(name)[1].lower()
        if ext in EXT_RULES:
            return EXT_RULES[ext]

    # 祖先兜底：最近的祖先优先。同一层先看知识库/AI笔记，再看目录名启发式——
    # 这样"Cache"类目录的子项会跟随父目录的判定，不会跳级冲突。
    parts = drive_rel.split("/")
    for i in range(len(parts) - 1, 0, -1):
        anc = "/".join(parts[:i])
        anc_name = parts[i - 1]
        anc_full = norm("C:/" + anc)
        if anc_full in ai_notes:
            n = ai_notes[anc_full]
            return n["safety"], "属于「" + n["title"] + "」的一部分。" + n["action"]
        r = match_rule(anc)
        if r is not None:
            return r["safety"], "属于「" + r["title"] + "」的一部分。" + r["action"]
        low_anc = anc_name.lower()
        for keys, safety, why in DIR_HINTS:
            if low_anc in keys or any(low_anc.startswith(k) for k in keys if len(k) > 4):
                return safety, "位于「" + anc_name + "」内——" + why
    return None, None


BROWSE_TIME_BUDGET = 6.0

def api_browse(path):
    """逐层浏览：列出目录下一级所有条目，每项带大小、修改时间、判定和理由。"""
    wp = to_win(path)
    if not os.path.isdir(wp):
        return {"error": "目录不存在或无法访问: " + path}
    drive_rel_base = path.split("/", 1)[1] if "/" in path else ""
    t0 = time.time()
    entries = []
    try:
        with os.scandir(wp) as it:
            listing = list(it)
    except OSError as e:
        return {"error": f"无法读取目录（{e.__class__.__name__}）"}
    n_dirs = sum(1 for e in listing if e.is_dir(follow_symlinks=False))
    per_dir_budget = max(0.3, BROWSE_TIME_BUDGET / max(n_dirs, 1))
    ai_notes = load_ai_notes_map()
    judged_before = _load_cache("ai_judge_cache.json").get(path, {})   # 历史 AI 判定
    for e in listing:
        try:
            st = e.stat(follow_symlinks=False)
            is_dir = e.is_dir(follow_symlinks=False)
            if is_dir:
                size, exact = quick_dir_size(e.path, per_dir_budget)
            else:
                size, exact = st.st_size, True
            rel = (drive_rel_base + "/" + e.name).strip("/")
            safety, why = judge_entry(rel, e.name, is_dir, ai_notes)
            if safety is None and e.name in judged_before:
                v = judged_before[e.name]
                safety, why = v.get("safety"), "（AI 记忆）" + v.get("why", "")
            entries.append({
                "name": e.name, "is_dir": is_dir, "size": size, "size_exact": exact,
                "mtime": time.strftime("%Y-%m-%d", time.localtime(st.st_mtime)),
                "safety": safety, "why": why,
            })
        except OSError:
            entries.append({"name": e.name, "is_dir": True, "size": 0, "size_exact": False,
                            "mtime": "", "safety": "none", "why": "无权限读取"})
    entries.sort(key=lambda x: -x["size"])
    return {"path": path, "entries": entries, "elapsed": round(time.time() - t0, 1)}


def quick_dir_size(path, budget):
    """限时目录大小估算。超时返回 (已累计, False=不精确)。"""
    t0, total = time.time(), 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                total += os.stat(os.path.join(root, f), follow_symlinks=False).st_size
            except OSError:
                pass
        if time.time() - t0 > budget:
            return total, False
    return total, True


def api_ai_judge(path, entries):
    """AI 批量判定未识别条目。entries = [{name, is_dir, size}]，最多 40 条。
    结果持久化到 ai_judge_cache.json，下次浏览同一目录自动带出。"""
    jcache = _load_cache("ai_judge_cache.json")
    known = jcache.get(path, {})
    fresh = [e for e in entries if e["name"] not in known]
    if not fresh:
        return {"verdicts": known, "cached": True}
    listing = [{"name": e["name"], "类型": "目录" if e.get("is_dir") else "文件",
                "大小MB": round(e.get("size", 0) / 1024 / 1024, 1)} for e in fresh[:40]]
    prompt = (
        "任务：逐条判定下列 Windows 条目（都位于 " + path + " 内）：每项是什么、能否删除。\n"
        "只输出一个 JSON 对象，无任何其他文字，格式：\n"
        "{\"条目名\": {\"safety\": \"safe|caution|user|danger|keep\", "
        "\"why\": \"是什么+能否删+删了什么后果，≤60字\"}}\n"
        "每个条目名必须与输入完全一致。禁止寒暄或解释。\n"
        + protected_clause() + "\n"
        "条目：" + json.dumps(listing, ensure_ascii=False)
    )
    if not CLAUDE_AVAILABLE:
        return {"error": AI_UNAVAILABLE_MSG}
    try:
        r = run_claude(prompt, 240)
        txt = (r.stdout or "").strip()
        if "```" in txt:
            txt = txt.split("```")[1]
            if txt.startswith("json"):
                txt = txt[4:]
        verdicts = json.loads(txt)
        known.update(verdicts)
        jcache[path] = known
        _save_cache("ai_judge_cache.json", jcache)
        return {"verdicts": known}
    except FileNotFoundError:
        return {"error": "未找到 claude 命令行"}
    except subprocess.TimeoutExpired:
        return {"error": "AI 判定超时（240秒）"}
    except (json.JSONDecodeError, IndexError):
        return {"error": "AI 输出无法解析"}


def api_detail(path):
    """深挖目录：最大文件 top15、扩展名分布 top8、最近修改时间。带时间预算。"""
    wp = to_win(path)
    if not os.path.isdir(wp):
        return {"error": "目录不存在或无法访问: " + path}
    t0 = time.time()
    biggest, ext_bytes = [], {}
    n_files, newest, truncated = 0, 0, False
    for root, dirs, files in os.walk(wp, onerror=lambda e: None):
        for f in files:
            fp = os.path.join(root, f)
            try:
                st = os.stat(fp, follow_symlinks=False)
            except OSError:
                continue
            n_files += 1
            newest = max(newest, st.st_mtime)
            ext = os.path.splitext(f)[1].lower() or "(无后缀)"
            ext_bytes[ext] = ext_bytes.get(ext, 0) + st.st_size
            biggest.append((st.st_size, fp, st.st_mtime))
            if len(biggest) > 400:
                biggest.sort(reverse=True)
                del biggest[100:]
        if time.time() - t0 > DETAIL_TIME_BUDGET or n_files > DETAIL_MAX_FILES:
            truncated = True
            break
    biggest.sort(reverse=True)
    return {
        "path": path,
        "file_count": n_files,
        "truncated": truncated,
        "newest_mtime": time.strftime("%Y-%m-%d", time.localtime(newest)) if newest else None,
        "days_since_change": round((time.time() - newest) / 86400) if newest else None,
        "top_files": [{"path": p[len(wp):].lstrip("\\"), "size": s,
                       "mtime": time.strftime("%Y-%m-%d", time.localtime(m))}
                      for s, p, m in biggest[:15]],
        "ext_stats": sorted(({"ext": k, "size": v} for k, v in ext_bytes.items()),
                            key=lambda x: -x["size"])[:8],
    }


def _load_cache(name):
    try:
        with open(os.path.join(OUT, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(name, data):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


CLAUDE_AVAILABLE = shutil.which("claude") is not None
AI_UNAVAILABLE_MSG = ("本机未安装 Claude CLI，AI 分析功能不可用（其他功能不受影响）。"
                      "安装 Claude Code (https://claude.com/claude-code) 后重启本服务即可启用。")


def protected_clause():
    """用户保护规则 → AI 提示词硬性条款。"""
    titles = protected_titles()
    if not titles:
        return "硬性规则：不确定的内容一律不建议删除。"
    return "硬性规则：以下内容用户要求永不删除，必须判为 keep——" + "、".join(titles) + "。"


def run_claude(prompt, timeout=180):
    """在中性目录运行 claude CLI，避免被本项目的 CLAUDE.md/记忆/模式污染回答。
    prompt 走 stdin——多行文本作为命令行参数会被 Windows cmd 在换行处截断。"""
    neutral = os.environ.get("TEMP") or os.path.expanduser("~")
    return subprocess.run("claude -p", input=prompt, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          shell=True, cwd=neutral)


def api_ai(path, context):
    """调用 claude CLI 做深度分析。context 是页面传来的已知信息（规则/大小等）。
    结果持久化到 ai_cache.json——同一目录不重复花钱花时间。"""
    cache = _load_cache("ai_cache.json")
    if path in cache and not context.get("force"):
        return {"text": cache[path], "cached": True}
    detail = api_detail(path)
    prompt = (
        "任务：分析 Windows 目录「" + path + "」能否清理。只根据下面提供的数据回答。\n\n"
        "【已知背景】" + json.dumps(context, ensure_ascii=False) + "\n"
        "【目录实测数据】（文件数、最近修改、最大文件、类型分布）：\n"
        + json.dumps(detail, ensure_ascii=False, default=str)[:4000] + "\n\n"
        "输出要求：直接输出分析正文，中文，≤250字，严格按此结构：\n"
        "这是什么：（一句话）\n"
        "里面有什么：（必须引用上面实测数据里的具体文件/子目录名和大小）\n"
        "能否删除：（能删多少、删了什么后果）\n"
        "建议操作：（具体步骤或命令）\n\n"
        "禁止：寒暄、自我介绍、复述任务、询问需求、谈论与该目录无关的任何内容。\n"
        + protected_clause()
    )
    if not CLAUDE_AVAILABLE:
        return {"error": AI_UNAVAILABLE_MSG, "detail": detail}
    try:
        r = run_claude(prompt, 180)
        txt = (r.stdout or "").strip()
        if txt:
            cache[path] = txt
            _save_cache("ai_cache.json", cache)
        return {"text": txt or "（AI 未返回内容）", "detail": detail}
    except FileNotFoundError:
        return {"error": "未找到 claude 命令行，无法进行 AI 分析", "detail": detail}
    except subprocess.TimeoutExpired:
        return {"error": "AI 分析超时（180秒）", "detail": detail}


def list_process_paths():
    """列出当前所有进程的 (pid, name, 可执行文件路径)。用 PowerShell CIM，无第三方依赖。"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        procs = json.loads(r.stdout or "[]")
        if isinstance(procs, dict):
            procs = [procs]
        return [(p.get("ProcessId"), p.get("Name"), p.get("ExecutablePath"))
                for p in procs if p.get("ExecutablePath")]
    except Exception:
        return []


def api_precheck(paths):
    """清理前的占用预检：是否有进程正从待清理目录里运行（uv/npx 这类缓存的典型风险）。"""
    procs = list_process_paths()
    results = []
    for path in paths:
        p = norm(path)
        hits = []
        for pid, name, exe in procs:
            if norm(exe).startswith(p + "/") or norm(exe) == p:
                hits.append({"pid": pid, "name": name})
        # 同名进程去重，最多列 5 个
        seen, uniq = set(), []
        for h in hits:
            if h["name"] not in seen:
                seen.add(h["name"])
                uniq.append(h)
        results.append({"path": path, "occupied": bool(hits),
                        "proc_count": len(hits), "procs": uniq[:5]})
    return {"results": results, "checked_procs": len(procs)}


def api_clean(paths, permanent=False):
    """清理白名单内的路径。默认移入隔离区；permanent=True 直接删除。
    只清空目录内容、保留目录本身（Temp 等目录需要存在）。"""
    wl = load_whitelist()
    ts = time.strftime("%Y%m%d_%H%M%S")
    # 服务端强制占用预检（不信任前端）：有进程正从目录里运行的项直接排除
    occupied = {r["path"]: r for r in api_precheck(paths)["results"] if r["occupied"]}
    results = []
    for path in paths:
        p = norm(path)
        if p not in wl:
            results.append({"path": path, "status": "拒绝", "note": "不在'可放心清理'白名单内，本工具只自动清理 ✅ 级项目"})
            continue
        if path in occupied:
            names = "、".join(x["name"] for x in occupied[path]["procs"])
            results.append({"path": path, "status": "已排除",
                            "note": f"检测到 {occupied[path]['proc_count']} 个进程正从此目录运行（{names}），"
                                    f"关闭相关程序后再清理"})
            continue
        wp = to_win(path)
        if not os.path.exists(wp):
            results.append({"path": path, "status": "跳过", "note": "路径不存在"})
            continue
        moved = skipped = 0
        moved_bytes = 0
        qdir = None
        if not permanent:
            qroot = quarantine_root(path)
            if not qroot:
                results.append({"path": path, "status": "失败", "note": "无法创建隔离区"})
                continue
            qdir = os.path.join(qroot, ts, p.replace(":", "").replace("/", "_"))
            os.makedirs(qdir, exist_ok=True)

        entries = [wp] if os.path.isfile(wp) else \
                  [os.path.join(wp, e) for e in os.listdir(wp)]
        mf_entries = []
        for src in entries:
            try:
                sz = dir_size(src) if os.path.isdir(src) else os.stat(src).st_size
                if permanent:
                    if os.path.isdir(src):
                        shutil.rmtree(src)
                    else:
                        os.remove(src)
                else:
                    shutil.move(src, os.path.join(qdir, os.path.basename(src)))
                    mf_entries.append({"src": src,
                                       "q": os.path.basename(qdir) + "\\" + os.path.basename(src)})
                moved += 1
                moved_bytes += sz
            except OSError:
                skipped += 1   # 正被占用的文件，跳过
        if not permanent and mf_entries:
            append_manifest(qroot, ts, mf_entries)
        results.append({"path": path, "status": "完成", "moved": moved, "skipped_inuse": skipped,
                        "bytes": moved_bytes, "quarantine": qdir})
    total = sum(r.get("bytes", 0) for r in results)
    # 记录清理日志，页面重新打开时据此标记"已清理"状态
    done = [{"path": r["path"], "bytes": r.get("bytes", 0), "permanent": permanent,
             "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            for r in results if r["status"] == "完成"]
    if done:
        log_file = os.path.join(OUT, "cleanup_log.json")
        try:
            with open(log_file, encoding="utf-8") as f:
                log = json.load(f)
        except (OSError, json.JSONDecodeError):
            log = {"entries": []}
        log["entries"].extend(done)
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=1)
    return {"results": results, "total_bytes": total, "permanent": permanent,
            "note": "已直接删除" if permanent else
                    "已移入隔离区（磁盘空间尚未释放）。确认系统一切正常后，点'清空隔离区'才会真正腾出空间。"}


# ---------- 重复文件查找（Czkawka 思路：按大小分组 -> 快速指纹） ----------
import hashlib

DUPE_BUDGET = 45.0

def quick_fingerprint(path, size):
    """快速指纹：文件头 1MB + 尾 64KB + 大小。对大文件避免全量哈希。"""
    h = hashlib.blake2b(digest_size=16)
    h.update(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))
        if size > 2 * 1024 * 1024:
            f.seek(-65536, 2)
            h.update(f.read(65536))
    return h.hexdigest()


def api_dupes(root, min_size_mb=10):
    """查找重复文件：同大小分组后比对快速指纹。返回按浪费空间排序的重复组。"""
    wp = to_win(root)
    if not os.path.isdir(wp):
        return {"error": "目录不存在: " + root}
    min_size = int(min_size_mb) * 1024 * 1024
    t0 = time.time()
    by_size = {}
    n_files, truncated = 0, False
    skip_names = {".c-cleaner-quarantine", "WinSxS", "System32", "SysWOW64"}
    for r_, dirs, files in os.walk(wp, onerror=lambda e: None):
        dirs[:] = [d for d in dirs if d not in skip_names]
        for fn in files:
            fp = os.path.join(r_, fn)
            try:
                st = os.stat(fp, follow_symlinks=False)
            except OSError:
                continue
            n_files += 1
            if st.st_size >= min_size:
                by_size.setdefault(st.st_size, []).append(fp)
        if time.time() - t0 > DUPE_BUDGET * 0.6:
            truncated = True
            break
    groups = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        if time.time() - t0 > DUPE_BUDGET:
            truncated = True
            break
        by_fp = {}
        for p in paths:
            try:
                by_fp.setdefault(quick_fingerprint(p, size), []).append(p)
            except OSError:
                continue
        for fp_, same in by_fp.items():
            if len(same) >= 2:
                groups.append({"size": size, "wasted": size * (len(same) - 1),
                               "files": [{"path": x.replace("\\", "/"),
                                          "mtime": time.strftime("%Y-%m-%d",
                                                   time.localtime(os.stat(x).st_mtime))}
                                         for x in sorted(same)]})
    groups.sort(key=lambda g: -g["wasted"])
    return {"root": root, "groups": groups[:50], "scanned_files": n_files,
            "truncated": truncated, "total_wasted": sum(g["wasted"] for g in groups),
            "note": "指纹=头1MB+尾64KB+大小，同指纹≈内容相同；删除前工具会再走判定和占用检查",
            "elapsed": round(time.time() - t0, 1)}


# ---------- 卸载残留检测（Bulk Crap Uninstaller 思路） ----------
def installed_programs():
    """从注册表读取已安装程序清单：名称集合 + 安装路径集合。"""
    import winreg
    names, locations = set(), set()
    roots = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
    for hive, base in roots:
        try:
            k = winreg.OpenKey(hive, base)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                sub = winreg.OpenKey(k, winreg.EnumKey(k, i))
                try:
                    name = winreg.QueryValueEx(sub, "DisplayName")[0]
                    names.add(str(name).lower())
                except OSError:
                    pass
                try:
                    loc = winreg.QueryValueEx(sub, "InstallLocation")[0]
                    if loc:
                        locations.add(norm(str(loc).replace("\\", "/")))
                except OSError:
                    pass
                winreg.CloseKey(sub)
            except OSError:
                continue
        winreg.CloseKey(k)
    return names, locations


LEFTOVER_SKIP = {"common files", "windowsapps", "windows defender", "windows mail",
                 "windows media player", "windows nt", "windows photo viewer",
                 "windowspowershell", "internet explorer", "microsoft", "microsoft.net",
                 "msbuild", "modifiablewindowsapps", "dotnet", "intel", "nvidia corporation",
                 "amd", "realtek", "dell", "reference assemblies", "uninstall information",
                 "microsoft office", "microsoft update health tools", "windows sidebar",
                 "common7", "wireguard", "7-zip"}


def api_leftovers():
    """疑似卸载残留：Program Files 等目录里，注册表已无对应已装程序的文件夹。"""
    names, locations = installed_programs()
    name_blob = " ".join(names)
    results = []
    bases = ["C:/Program Files", "C:/Program Files (x86)",
             os.environ.get("LOCALAPPDATA", "").replace("\\", "/") + "/Programs"]
    for base in bases:
        wb = to_win(base)
        if not os.path.isdir(wb):
            continue
        try:
            entries = list(os.scandir(wb))
        except OSError:
            continue
        for e in entries:
            if not e.is_dir(follow_symlinks=False):
                continue
            low = e.name.lower()
            if low in LEFTOVER_SKIP or low.startswith(("windows", "microsoft")):
                continue
            full_n = norm(base + "/" + e.name)
            # 判据1：InstallLocation 覆盖 -> 在装
            if any(loc and (full_n == loc or full_n.startswith(loc + "/") or loc.startswith(full_n + "/"))
                   for loc in locations):
                continue
            # 判据2：目录名词元出现在任一已装程序名里 -> 可能在装
            tokens = [t for t in __import__("re").split(r"[\s\-_.]+", low) if len(t) >= 3]
            if tokens and any(t in name_blob for t in tokens):
                continue
            try:
                st = e.stat(follow_symlinks=False)
                size, exact = quick_dir_size(e.path, 0.8)
            except OSError:
                continue
            if size < 5 * 1024 * 1024:
                continue
            results.append({"path": base + "/" + e.name, "size": size, "size_exact": exact,
                            "mtime": time.strftime("%Y-%m-%d", time.localtime(st.st_mtime))})
    results.sort(key=lambda x: -x["size"])
    return {"items": results, "installed_count": len(names),
            "note": "启发式判断：注册表已装清单里找不到对应程序的目录。删除前请自行确认软件确实已卸载！"}


SAFE_SCAN_BUDGET = 12.0

def api_safe_scan(root):
    """递归汇总 root 下所有判定为 safe 的最外层条目（safe 目录不再深入，取最小覆盖集）。"""
    wp = to_win(root)
    if not os.path.isdir(wp):
        return {"error": "目录不存在: " + root}
    ai_notes = load_ai_notes_map()
    base_rel = root.split("/", 1)[1] if "/" in root else ""
    t0 = time.time()
    out = []
    truncated = [False]

    def rec(dirpath, rel_from_root, depth):
        if truncated[0] or depth > 5:
            return
        try:
            with os.scandir(dirpath) as it:
                listing = list(it)
        except OSError:
            return
        for e in listing:
            if time.time() - t0 > SAFE_SCAN_BUDGET or len(out) >= 300:
                truncated[0] = True
                return
            try:
                is_dir = e.is_dir(follow_symlinks=False)
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if e.name == ".c-cleaner-quarantine":
                continue
            erel_root = (rel_from_root + "/" + e.name).strip("/")
            drive_rel = (base_rel + "/" + erel_root).strip("/")
            safety, why = judge_entry(drive_rel, e.name, is_dir, ai_notes)
            if safety == "safe":
                if is_dir:
                    size, exact = quick_dir_size(e.path, 1.0)
                else:
                    size, exact = st.st_size, True
                if size >= 1024 * 1024:   # 小于 1MB 的不值得列
                    out.append({"path": root + "/" + erel_root, "rel": erel_root,
                                "is_dir": is_dir, "size": size, "size_exact": exact,
                                "why": why})
                # safe 目录整个可删，不再深入列它的子项
            elif is_dir and safety not in ("keep", "danger"):
                rec(e.path, erel_root, depth + 1)

    rec(wp, "", 0)
    out.sort(key=lambda x: -x["size"])
    return {"root": root, "items": out, "truncated": truncated[0],
            "total": sum(x["size"] for x in out),
            "elapsed": round(time.time() - t0, 1)}


def api_clean_paths(paths, permanent=False):
    """批量删除完整路径列表（安全汇总列表的提交入口）。逐项重新判定+占用检查。"""
    ai_notes = load_ai_notes_map()
    procs = list_process_paths()
    ts = time.strftime("%Y%m%d_%H%M%S")
    results = []
    for full in paths:
        wp = to_win(full)
        name = os.path.basename(wp)
        if not os.path.exists(wp):
            results.append({"path": full, "status": "跳过", "note": "已不存在"})
            continue
        is_dir = os.path.isdir(wp)
        drive_rel = full.split("/", 1)[1] if "/" in full else ""
        safety, why = judge_entry(drive_rel, name, is_dir, ai_notes)
        if safety in ("keep", "danger"):
            results.append({"path": full, "status": "拒绝", "note": "判定为不可删级别"})
            continue
        full_n = norm(full)
        hit = [p for p in procs if norm(p[2]).startswith(full_n + "/") or norm(p[2]) == full_n]
        if hit:
            names_s = "、".join(sorted({h[1] for h in hit})[:4])
            results.append({"path": full, "status": "拒绝",
                            "note": f"有进程正从这里运行（{names_s}）"})
            continue
        try:
            sz = dir_size(wp) if is_dir else os.stat(wp).st_size
            if permanent:
                shutil.rmtree(wp) if is_dir else os.remove(wp)
            else:
                qroot = quarantine_root(full)
                if not qroot:
                    results.append({"path": full, "status": "失败", "note": "无法创建隔离区"})
                    continue
                parent_tag = norm(os.path.dirname(full)).replace(":", "").replace("/", "_")
                qdir = os.path.join(qroot, ts, parent_tag)
                os.makedirs(qdir, exist_ok=True)
                shutil.move(wp, os.path.join(qdir, name))
                append_manifest(qroot, ts, [{"src": wp, "q": parent_tag + "\\" + name}])
            results.append({"path": full, "status": "完成", "bytes": sz})
        except OSError as e:
            results.append({"path": full, "status": "失败", "note": e.__class__.__name__})
    total = sum(r.get("bytes", 0) for r in results)
    return {"results": results, "total_bytes": total, "permanent": permanent}


def api_clean_items(base, names, permanent=False):
    """逐项浏览界面的勾选删除：删除 base 目录下指定条目（文件或子目录）。
    keep/danger 级拒绝；进程占用拒绝；默认移入隔离区。"""
    wp = to_win(base)
    if not os.path.isdir(wp):
        return {"error": "目录不存在: " + base}
    drive_rel_base = base.split("/", 1)[1] if "/" in base else ""
    ai_notes = load_ai_notes_map()
    procs = list_process_paths()
    ts = time.strftime("%Y%m%d_%H%M%S")
    qdir = None
    if not permanent:
        qroot = quarantine_root(base)
        if not qroot:
            return {"error": "无法创建隔离区"}
        qdir = os.path.join(qroot, ts, norm(base).replace(":", "").replace("/", "_"))
    results = []
    for name in names:
        # 防路径穿越
        if "/" in name or "\\" in name or name in (".", ".."):
            results.append({"name": name, "status": "拒绝", "note": "非法名称"})
            continue
        src = os.path.join(wp, name)
        if not os.path.exists(src):
            results.append({"name": name, "status": "跳过", "note": "已不存在"})
            continue
        is_dir = os.path.isdir(src)
        rel = (drive_rel_base + "/" + name).strip("/")
        safety, why = judge_entry(rel, name, is_dir, ai_notes)
        if safety in ("keep", "danger"):
            results.append({"name": name, "status": "拒绝",
                            "note": "判定为「" + ("系统必需/保留" if safety == "keep" else "不建议手动删") + "」：" + (why or "")})
            continue
        src_n = norm(src.replace("\\", "/"))
        hit = [p for p in procs if norm(p[2]).startswith(src_n + "/") or norm(p[2]) == src_n]
        if hit:
            names_s = "、".join(sorted({h[1] for h in hit})[:4])
            results.append({"name": name, "status": "拒绝",
                            "note": f"有 {len(hit)} 个进程正从这里运行（{names_s}），先关闭相关程序"})
            continue
        try:
            sz = dir_size(src) if is_dir else os.stat(src).st_size
            if permanent:
                if is_dir:
                    shutil.rmtree(src)
                else:
                    os.remove(src)
            else:
                os.makedirs(qdir, exist_ok=True)
                shutil.move(src, os.path.join(qdir, name))
                append_manifest(qroot, ts,
                                [{"src": src, "q": os.path.basename(qdir) + "\\" + name}])
            results.append({"name": name, "status": "完成", "bytes": sz})
        except OSError as e:
            results.append({"name": name, "status": "失败", "note": e.__class__.__name__ + "（可能被占用）"})
    total = sum(r.get("bytes", 0) for r in results)
    return {"results": results, "total_bytes": total, "permanent": permanent, "quarantine": qdir}


# ---------- 隔离区：manifest / 复检 / 还原 ----------
def append_manifest(qroot, ts, entries):
    """记录被隔离文件的原路径，清空前复检和还原都靠它（同回收站 $I 元数据的思路）。"""
    if not entries:
        return
    mf = os.path.join(qroot, ts, "manifest.json")
    try:
        with open(mf, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {"entries": []}
    data["entries"].extend(entries)
    os.makedirs(os.path.dirname(mf), exist_ok=True)
    with open(mf, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# 不可再生特征：出现在"缓存"里就非常可疑的文件类型
SUSPICIOUS_EXT = {
    ".doc": "文档", ".docx": "文档", ".xls": "表格", ".xlsx": "表格",
    ".ppt": "演示文稿", ".pptx": "演示文稿", ".pdf": "PDF 文档",
    ".psd": "Photoshop 源文件", ".ai": "Illustrator 源文件", ".aep": "AE 工程",
    ".prproj": "PR 工程", ".3dm": "Rhino 模型", ".blend": "Blender 工程",
    ".skp": "SketchUp 模型", ".fig": "Figma 文件",
    ".sqlite": "数据库", ".sqlite3": "数据库", ".mdb": "数据库", ".accdb": "数据库",
    ".sav": "游戏存档", ".save": "游戏存档",
    ".kdbx": "密码库！", ".pfx": "证书密钥！", ".pem": "证书密钥！", ".key": "密钥！",
}
MEDIA_EXT = {".jpg", ".jpeg", ".png", ".heic", ".cr2", ".raw", ".mp4", ".mov", ".mkv"}
ARCHIVE_EXT = {".zip", ".7z", ".rar"}
TS_RE = __import__("re").compile(r"^\d{8}_\d{6}$")


def quarantine_roots():
    roots = []
    for d in ("C", "D"):
        r = d + ":\\.c-cleaner-quarantine"
        if os.path.isdir(r):
            roots.append(r)
    la = os.path.join(os.environ.get("LOCALAPPDATA", ""), "c-cleaner", "quarantine")
    if os.path.isdir(la):
        roots.append(la)
    return roots


def check_file_suspicion(name, size):
    """单文件复检：返回可疑原因或 None。"""
    ext = os.path.splitext(name)[1].lower()
    if ext in SUSPICIOUS_EXT:
        return SUSPICIOUS_EXT[ext] + "——通常不可再生"
    if ext in MEDIA_EXT and size >= 2 * 1024 * 1024:
        return "较大媒体文件——若是你拍的/做的，删了找不回"
    if ext in ARCHIVE_EXT and size >= 10 * 1024 * 1024:
        return "大压缩包——确认里面内容不再需要"
    return None


def api_quarantine_review():
    """清空前复检：逐个文件检查每个批次，标出不可再生特征。"""
    batches = {}
    for root in quarantine_roots():
        try:
            ts_dirs = [d for d in os.listdir(root) if TS_RE.match(d)]
        except OSError:
            continue
        for ts in ts_dirs:
            bdir = os.path.join(root, ts)
            b = batches.setdefault(ts, {"batch": ts, "file_count": 0, "total_bytes": 0,
                                        "suspicious": [], "sources": set(), "has_manifest": False})
            mf = os.path.join(bdir, "manifest.json")
            if os.path.isfile(mf):
                b["has_manifest"] = True
                try:
                    with open(mf, encoding="utf-8") as f:
                        for en in json.load(f).get("entries", []):
                            b["sources"].add(os.path.dirname(en["src"]))
                except (OSError, json.JSONDecodeError):
                    pass
            for r_, dirs, files in os.walk(bdir, onerror=lambda e: None):
                for fn in files:
                    if fn == "manifest.json":
                        continue
                    fp = os.path.join(r_, fn)
                    try:
                        sz = os.stat(fp, follow_symlinks=False).st_size
                    except OSError:
                        continue
                    b["file_count"] += 1
                    b["total_bytes"] += sz
                    reason = check_file_suspicion(fn, sz)
                    if reason and len(b["suspicious"]) < 50:
                        b["suspicious"].append({
                            "file": os.path.relpath(fp, bdir), "size": sz, "reason": reason})
    out = []
    for ts in sorted(batches, reverse=True):
        b = batches[ts]
        b["sources"] = sorted(b["sources"])[:6]
        b["suspicious"].sort(key=lambda x: -x["size"])
        out.append(b)
    return {"batches": out}


def api_quarantine_restore(batch):
    """按 manifest 把整个批次还原回原位。原位已有同名文件则跳过（保留在隔离区）。"""
    if not TS_RE.match(batch or ""):
        return {"error": "非法批次号"}
    restored, skipped, failed = 0, [], []
    restored_bytes = 0
    for root in quarantine_roots():
        bdir = os.path.join(root, batch)
        mf = os.path.join(bdir, "manifest.json")
        if not os.path.isfile(mf):
            continue
        try:
            with open(mf, encoding="utf-8") as f:
                entries = json.load(f).get("entries", [])
        except (OSError, json.JSONDecodeError):
            continue
        remaining = []
        for en in entries:
            src_q = os.path.join(bdir, en["q"])
            dst = en["src"]
            if not os.path.exists(src_q):
                continue
            if os.path.exists(dst):
                skipped.append(dst)
                remaining.append(en)
                continue
            try:
                sz = dir_size(src_q) if os.path.isdir(src_q) else os.stat(src_q).st_size
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src_q, dst)
                restored += 1
                restored_bytes += sz
            except OSError as e:
                failed.append(dst + " (" + e.__class__.__name__ + ")")
                remaining.append(en)
        if remaining:
            with open(mf, "w", encoding="utf-8") as f:
                json.dump({"entries": remaining}, f, ensure_ascii=False)
        else:
            shutil.rmtree(bdir, ignore_errors=True)
    return {"restored": restored, "restored_bytes": restored_bytes,
            "skipped_exists": skipped[:20], "failed": failed[:20]}


def api_quarantine(action, batch=None):
    roots = quarantine_roots()
    if action == "status":
        total = sum(dir_size(r) for r in roots)
        oldest_days = None
        for r in roots:
            try:
                ts_dirs = [d for d in os.listdir(r) if TS_RE.match(d)]
            except OSError:
                continue
            for tsd in ts_dirs:
                try:
                    t = time.mktime(time.strptime(tsd, "%Y%m%d_%H%M%S"))
                except ValueError:
                    continue
                days = int((time.time() - t) // 86400)
                oldest_days = days if oldest_days is None else max(oldest_days, days)
        return {"roots": roots, "total_bytes": total, "oldest_days": oldest_days}
    if action == "empty":
        freed = 0
        if batch:                     # 只清指定批次
            if not TS_RE.match(batch):
                return {"error": "非法批次号"}
            for r in roots:
                bdir = os.path.join(r, batch)
                if os.path.isdir(bdir):
                    freed += dir_size(bdir)
                    shutil.rmtree(bdir, ignore_errors=True)
        else:                         # 清全部
            for r in roots:
                freed += dir_size(r)
                shutil.rmtree(r, ignore_errors=True)
        return {"freed_bytes": freed}
    return {"error": "unknown action"}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 安静

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/report", "/report.html"):
            try:
                with open(os.path.join(OUT, "report.html"), "rb") as f:
                    html = f.read()
                inject = ("<script>window.CC_TOKEN='" + TOKEN + "';</script><script>").encode()
                html = html.replace(b"<script>", inject, 1)
                self._send(200, html, "text/html; charset=utf-8")
            except OSError:
                self._send(404, {"error": "report.html 不存在，请先运行 python main.py"})
        elif self.path == "/api/ping":
            self._send(200, {"ok": True, "version": "1.3", "ai_available": CLAUDE_AVAILABLE})
        elif self.path == "/api/cleanlog":
            try:
                with open(os.path.join(OUT, "cleanup_log.json"), encoding="utf-8") as f:
                    self._send(200, json.load(f))
            except (OSError, json.JSONDecodeError):
                self._send(200, {"entries": []})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.headers.get("X-CC-Token") != TOKEN:
            self._send(403, {"error": "缺少或错误的访问令牌——请通过报告页面操作"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "bad json"})
            return
        try:
            if self.path == "/api/rescan":
                # 重新走一遍 扫描→分析→出报告（20~60秒），完成后页面自行 reload
                with open(os.path.join(OUT, "analysis.json"), encoding="utf-8") as f:
                    target = json.load(f)["meta"]["target"]
                for script, args in (("scanner.py", [target, os.path.join(OUT, "scan_result.json")]),
                                     ("analyze.py", [os.path.join(OUT, "scan_result.json"), os.path.join(OUT, "analysis.json")]),
                                     ("report.py", [])):
                    subprocess.run([sys.executable, os.path.join(HERE, script)] + args,
                                   cwd=HERE, check=True, capture_output=True, timeout=600)
                self._send(200, {"ok": True})
            elif self.path == "/api/precheck":
                self._send(200, api_precheck(req.get("paths", [])))
            elif self.path == "/api/browse":
                self._send(200, api_browse(req["path"]))
            elif self.path == "/api/ai_judge":
                self._send(200, api_ai_judge(req["path"], req.get("entries", [])))
            elif self.path == "/api/dupes":
                self._send(200, api_dupes(req.get("path", "C:/Users/" + os.environ.get("USERNAME", "")),
                                          req.get("min_size_mb", 10)))
            elif self.path == "/api/leftovers":
                self._send(200, api_leftovers())
            elif self.path == "/api/safe_scan":
                self._send(200, api_safe_scan(req["path"]))
            elif self.path == "/api/clean_paths":
                self._send(200, api_clean_paths(req.get("paths", []), bool(req.get("permanent"))))
            elif self.path == "/api/clean_items":
                self._send(200, api_clean_items(req["base"], req.get("names", []),
                                                bool(req.get("permanent"))))
            elif self.path == "/api/detail":
                self._send(200, api_detail(req["path"]))
            elif self.path == "/api/ai":
                self._send(200, api_ai(req["path"], req.get("context", {})))
            elif self.path == "/api/clean":
                self._send(200, api_clean(req.get("paths", []), bool(req.get("permanent"))))
            elif self.path == "/api/quarantine":
                self._send(200, api_quarantine(req.get("action", "status"), req.get("batch")))
            elif self.path == "/api/quarantine_review":
                self._send(200, api_quarantine_review())
            elif self.path == "/api/quarantine_restore":
                self._send(200, api_quarantine_restore(req.get("batch")))
            else:
                self._send(404, {"error": "not found"})
        except Exception as e:  # 页面上要能看到错误
            self._send(500, {"error": f"{e.__class__.__name__}: {e}"})


def main():
    addr = ("127.0.0.1", PORT)
    httpd = http.server.ThreadingHTTPServer(addr, Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"[serve] 报告服务已启动: {url}  (Ctrl+C 停止)")
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
