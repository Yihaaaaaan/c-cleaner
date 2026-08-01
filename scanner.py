# -*- coding: utf-8 -*-
r"""
scanner.py — 磁盘扫描引擎
递归扫描指定盘符/目录，统计每个目录的占用空间，输出 JSON 树。

设计要点（参考 SpaceSniffer 的行为）：
- 使用 os.scandir 快速遍历
- 跳过 junction / symlink（reparse point），避免死循环和重复计数
- 使用 \\?\ 长路径前缀，避免超过 MAX_PATH 报错
- 权限不足的目录记录下来，不中断扫描
- 输出时裁剪：只保留大于阈值的节点，避免 JSON 过大
"""
import os
import sys
import json

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import time
import stat as stat_mod
import shutil

FILE_ATTRIBUTE_REPARSE_POINT = 0x400

# 输出裁剪阈值：小于该值的子节点合并为 "(其他小文件)"
DEFAULT_PRUNE_BYTES = 50 * 1024 * 1024  # 50 MB
# 单个大文件单独列出的阈值
BIG_FILE_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_DEPTH_KEEP = 8  # 输出树最大深度（扫描本身不限深度）


def _is_reparse_point(entry):
    try:
        st = entry.stat(follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False


def scan_dir(path, errors, file_count_box):
    """递归扫描目录，返回节点 dict：{name, size, dirs: {...}, big_files: [...]}"""
    total = 0
    children = {}
    big_files = []
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except OSError as e:
        errors.append({"path": strip_prefix(path), "error": e.__class__.__name__})
        return {"size": 0, "dirs": {}, "big_files": [], "denied": True}

    for entry in entries:
        try:
            if _is_reparse_point(entry):
                continue  # junction / symlink：不跟进也不计数
            if entry.is_dir(follow_symlinks=False):
                node = scan_dir(entry.path, errors, file_count_box)
                total += node["size"]
                children[entry.name] = node
            elif entry.is_file(follow_symlinks=False):
                sz = entry.stat(follow_symlinks=False).st_size
                total += sz
                file_count_box[0] += 1
                if sz >= BIG_FILE_BYTES:
                    big_files.append({"name": entry.name, "size": sz})
        except OSError as e:
            errors.append({"path": strip_prefix(entry.path), "error": e.__class__.__name__})

    return {"size": total, "dirs": children, "big_files": big_files}


def strip_prefix(p):
    if p.startswith("\\\\?\\"):
        return p[4:]
    return p


def prune(node, threshold, depth=0):
    """裁剪输出树：合并小目录，限制深度。"""
    out = {"size": node["size"]}
    if node.get("denied"):
        out["denied"] = True
    if depth >= MAX_DEPTH_KEEP:
        return out
    kept = {}
    other = 0
    for name, child in node.get("dirs", {}).items():
        if child["size"] >= threshold or child.get("denied"):
            kept[name] = prune(child, threshold, depth + 1)
        else:
            other += child["size"]
    if kept:
        out["dirs"] = kept
    if other > 0:
        out["other_dirs_size"] = other
    bf = [f for f in node.get("big_files", []) if f["size"] >= BIG_FILE_BYTES]
    if bf:
        out["big_files"] = sorted(bf, key=lambda x: -x["size"])[:20]
    return out


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "C:\\"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "output/scan_result.json"
    prune_bytes = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_PRUNE_BYTES

    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)

    # 长路径前缀
    root = target if target.startswith("\\\\?\\") else "\\\\?\\" + os.path.abspath(target)

    t0 = time.time()
    errors = []
    file_count_box = [0]
    print(f"[scanner] 开始扫描 {target} ...", flush=True)
    tree = scan_dir(root, errors, file_count_box)
    elapsed = time.time() - t0

    # 磁盘整体用量对比（扫描不到的部分 = 系统保护区/权限不足/NTFS元数据）
    drive = os.path.splitdrive(os.path.abspath(target))[0] + "\\"
    du = shutil.disk_usage(drive)

    result = {
        "target": os.path.abspath(target),
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": round(elapsed, 1),
        "file_count": file_count_box[0],
        "disk_total": du.total,
        "disk_used": du.used,
        "disk_free": du.free,
        "scanned_size": tree["size"],
        "unscanned_size": max(0, du.used - tree["size"]),
        "error_count": len(errors),
        "errors_sample": errors[:200],
        "tree": prune(tree, prune_bytes),
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    gb = tree["size"] / 1024**3
    print(f"[scanner] 完成：{file_count_box[0]:,} 个文件，共 {gb:.1f} GB，"
          f"耗时 {elapsed:.0f} 秒，{len(errors)} 个目录无权限，结果已存 {out_file}", flush=True)


if __name__ == "__main__":
    main()
