# -*- coding: utf-8 -*-
r"""
winapp2.py — Winapp2.ini 社区规则库导入器

把 MoscaDotTo/Winapp2（4000+ 条社区清理规则，CC-BY-SA-4.0）转换成本工具的规则格式：
  1. 解析 INI（Detect/DetectFile/FileKey/Warning）
  2. 在本机评估 Detect 条件（注册表/文件存在），只保留"本机装了对应软件"的条目
  3. FileKey 转换为目录级规则，输出 output/winapp2_rules.json

安全映射（关键！）：
  - FileKey 是"整目录内容可删"（pattern=* 且 RECURSE/REMOVESELF）→ safe
  - FileKey 只删特定文件类型（如 *.log、*Web Data）→ caution，desc 写明只能删哪些
  - 带 Warning 字段 → 一律 caution，Warning 原文进 action

用法: python winapp2.py [data/winapp2.ini] [output/winapp2_rules.json]
"""
import os
import re
import sys
import json
import glob as globmod

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import winreg
except ImportError:
    winreg = None


def env_map():
    e = os.environ
    up = e.get("USERPROFILE", r"C:\Users\Default")
    m = {
        "%appdata%": e.get("APPDATA", up + r"\AppData\Roaming"),
        "%localappdata%": e.get("LOCALAPPDATA", up + r"\AppData\Local"),
        "%locallowappdata%": up + r"\AppData\LocalLow",
        "%userprofile%": up,
        "%windir%": e.get("WINDIR", r"C:\Windows"),
        "%systemdrive%": e.get("SYSTEMDRIVE", "C:"),
        "%systemroot%": e.get("SYSTEMROOT", r"C:\Windows"),
        "%programfiles%": e.get("PROGRAMFILES", r"C:\Program Files"),
        "%programfiles(x86)%": e.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        "%commonprogramfiles%": e.get("COMMONPROGRAMFILES", r"C:\Program Files\Common Files"),
        "%commonappdata%": e.get("PROGRAMDATA", r"C:\ProgramData"),
        "%programdata%": e.get("PROGRAMDATA", r"C:\ProgramData"),
        "%public%": e.get("PUBLIC", r"C:\Users\Public"),
        "%documents%": up + r"\Documents",
        "%pictures%": up + r"\Pictures",
        "%music%": up + r"\Music",
        "%video%": up + r"\Videos",
        "%downloads%": up + r"\Downloads",
        "%desktop%": up + r"\Desktop",
        "%temp%": e.get("TEMP", up + r"\AppData\Local\Temp"),
        "%tmp%": e.get("TEMP", up + r"\AppData\Local\Temp"),
        "%homedrive%": e.get("HOMEDRIVE", "C:"),
    }
    return m


ENV = env_map()
VAR_RE = re.compile(r"%[^%]+%")


def expand(path):
    def rep(mo):
        return ENV.get(mo.group(0).lower(), mo.group(0))
    return VAR_RE.sub(rep, path)


HIVES = {
    "HKCU": "HKEY_CURRENT_USER", "HKLM": "HKEY_LOCAL_MACHINE",
    "HKCR": "HKEY_CLASSES_ROOT", "HKU": "HKEY_USERS",
    "HKEY_CURRENT_USER": "HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE": "HKEY_LOCAL_MACHINE",
    "HKEY_CLASSES_ROOT": "HKEY_CLASSES_ROOT", "HKEY_USERS": "HKEY_USERS",
}


def reg_exists(path):
    if winreg is None:
        return False
    parts = path.split("\\", 1)
    hive_name = HIVES.get(parts[0].upper())
    if not hive_name or len(parts) < 2:
        return False
    hive = getattr(winreg, hive_name)
    for access in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                   winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
        try:
            winreg.CloseKey(winreg.OpenKey(hive, parts[1], 0, access))
            return True
        except OSError:
            continue
    return False


def file_detect(path):
    p = expand(path)
    if "*" in p or "?" in p:
        try:
            return bool(globmod.glob(p))
        except (OSError, ValueError):
            return False
    return os.path.exists(p)


def parse_ini(text):
    """返回 [(section, {key: [values...]})]，同名键（FileKey1..N）合并进列表。"""
    entries = []
    cur, cur_name = None, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            if cur_name is not None:
                entries.append((cur_name, cur))
            cur_name, cur = line[1:-1], {}
            continue
        if cur is None or "=" not in line:
            continue
        k, v = line.split("=", 1)
        base = re.sub(r"\d+$", "", k.strip())   # FileKey1 -> FileKey
        cur.setdefault(base.lower(), []).append(v.strip())
    if cur_name is not None:
        entries.append((cur_name, cur))
    return entries


def entry_active(keys):
    """Detect 条件评估：多条 Detect 之间是 OR；完全没有 Detect 视为通用条目（激活）。"""
    detects = keys.get("detect", [])
    dfiles = keys.get("detectfile", [])
    if not detects and not dfiles:
        return True
    for d in detects:
        if reg_exists(d):
            return True
    for d in dfiles:
        if file_detect(d):
            return True
    return False


def to_drive_rel(win_path):
    r"""C:\Users\xx\... -> users/xx/...；非 C 盘返回 None。"""
    p = win_path.replace("/", "\\")
    if len(p) < 2 or p[1] != ":":
        return None
    if p[0].upper() != "C":
        return None
    return p[2:].strip("\\").replace("\\", "/")


def convert(entries):
    """激活条目的 FileKey → 目录级规则。按目录合并，安全等级取最保守。"""
    by_dir = {}
    active_sections = 0
    for name, keys in entries:
        if "filekey" not in keys:
            continue
        if not entry_active(keys):
            continue
        active_sections += 1
        title = re.sub(r"\s*\*\s*$", "", name)
        warning = "；".join(keys.get("warning", [])) or None
        for fk in keys["filekey"]:
            parts = fk.split("|")
            if not parts:
                continue
            raw_dir = expand(parts[0])
            patterns = parts[1].split(";") if len(parts) > 1 else ["*"]
            flags = [x.upper() for x in parts[2:]]
            rel = to_drive_rel(raw_dir)
            if not rel:
                continue
            full_content = (all(pt.strip() in ("*", "*.*") for pt in patterns)
                            and ("RECURSE" in flags or "REMOVESELF" in flags))
            key = rel.lower()
            b = by_dir.setdefault(key, {"rel": rel, "titles": set(), "patterns": set(),
                                        "full": False, "warning": None})
            b["titles"].add(title)
            b["patterns"].update(pt.strip() for pt in patterns)
            b["full"] = b["full"] or full_content
            if warning:
                b["warning"] = (b["warning"] + "；" + warning) if b["warning"] else warning

    # 隐私类条目：winapp2 的定位是"隐私+垃圾"双清理，其中隐私类（自动填充、
    # 历史、Cookies、会话…）删的是用户数据不是垃圾——降级为 user 级，绝不标 safe
    privacy_pat = ("autofill", "password", "history", "cookie", "session", "bookmark",
                   "login", "form data", "saved", "credential", "sync data", "tabs",
                   "most visited", "top sites", "recent", "mru", "typed url", "wallet",
                   "web storage", "indexeddb", "local storage", "site data")
    rules = []
    for key, b in by_dir.items():
        title = "、".join(sorted(b["titles"])[:2])
        pats = sorted(b["patterns"])
        pat_txt = "、".join(pats[:6]) + ("…" if len(pats) > 6 else "")
        titles_low = " ".join(b["titles"]).lower()
        is_privacy = any(k in titles_low for k in privacy_pat)
        if is_privacy:
            safety = "user"
            action = ("这是隐私/使用记录类数据（自动填充、历史、登录状态等）——"
                      "删除的意义是保护隐私，不是清垃圾；删了要重新登录/记录会丢，自行决定")
        elif b["warning"]:
            safety = "caution"
            action = "⚠ Winapp2 警告：" + b["warning"][:200]
        elif b["full"]:
            safety = "safe"
            action = "该目录内容可清理（社区规则确认为缓存/垃圾类）"
        else:
            safety = "caution"
            action = f"只可删其中匹配 {pat_txt} 的文件，不要删整个目录"
        rules.append({
            "pattern": b["rel"], "title": "[Winapp2] " + title, "safety": safety,
            "desc": f"社区规则库 Winapp2 收录的「{title}」清理项。"
                    + ("整个目录内容判定为可清理。" if b["full"] and not b["warning"]
                       else f"可清理文件类型：{pat_txt}。"),
            "action": action, "src": "winapp2",
        })
    return rules, active_sections


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "data/winapp2.ini"
    dst = sys.argv[2] if len(sys.argv) > 2 else "output/winapp2_rules.json"
    with open(src, encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    entries = parse_ini(text)
    print(f"[winapp2] 解析 {len(entries)} 个条目，评估本机 Detect 条件…")
    rules, active = convert(entries)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"version": "MoscaDotTo/Winapp2 (CC-BY-SA-4.0)",
                   "active_sections": active, "rules": rules}, f, ensure_ascii=False, indent=1)
    n_safe = sum(1 for r in rules if r["safety"] == "safe")
    print(f"[winapp2] 本机激活 {active} 个条目 → 生成 {len(rules)} 条目录规则"
          f"（safe {n_safe} / caution {len(rules)-n_safe}），已存 {dst}")


if __name__ == "__main__":
    main()
