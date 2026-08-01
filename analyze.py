# -*- coding: utf-8 -*-
"""
analyze.py — 把扫描结果和知识库对上号

输入 scan_result.json，输出 analysis.json：
- findings: 识别出的占空间大户列表（含说明、安全等级、清理方法），按大小排序
- unknowns: 知识库没认出来的大目录（交给 AI 进一步分析）
- tree 上每个节点补充 rule 信息，供报告的 treemap 使用
"""
import sys
import json

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from knowledge import match_rule, SAFETY_LABEL

MIN_FINDING = 100 * 1024 * 1024      # 识别项 ≥100MB 才进列表
MIN_UNKNOWN = 1024 * 1024 * 1024     # 未识别项 ≥1GB 才标记给 AI
UNKNOWN_MAX_DEPTH = 6


def walk(name, node, rel_path, depth, parent_rule, findings, unknowns,
         ancestor_unknown=False):
    rule = match_rule(rel_path) if rel_path else None
    node["rule"] = None
    is_unknown_here = False
    if rule is not None:
        node["rule"] = {
            "title": rule["title"], "safety": rule["safety"],
            "desc": rule["desc"], "action": rule["action"],
        }
        is_new_match = rule is not parent_rule
        if is_new_match and node["size"] >= MIN_FINDING:
            findings.append({
                "path": "C:/" + rel_path, "size": node["size"],
                "title": rule["title"], "safety": rule["safety"],
                "desc": rule["desc"], "action": rule["action"],
            })
    else:
        # 未识别的大目录：只报最外层，不重复报它的子目录。
        # 父规则是"结构性目录"（Users、AppData 这类容器）时，未知子目录仍然要冒出来。
        parent_is_container = parent_rule is None or parent_rule.get("structural")
        if node["size"] >= MIN_UNKNOWN and depth <= UNKNOWN_MAX_DEPTH \
                and parent_is_container and rel_path and not ancestor_unknown:
            unknowns.append({"path": "C:/" + rel_path, "size": node["size"],
                             "denied": bool(node.get("denied"))})
            is_unknown_here = True

    for child_name, child in node.get("dirs", {}).items():
        child_rel = (rel_path + "/" + child_name) if rel_path else child_name
        walk(child_name, child, child_rel, depth + 1,
             rule if rule is not None else parent_rule, findings, unknowns,
             ancestor_unknown or is_unknown_here)


def main():
    in_file = sys.argv[1] if len(sys.argv) > 1 else "output/scan_result.json"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "output/analysis.json"

    with open(in_file, encoding="utf-8") as f:
        scan = json.load(f)

    findings, unknowns = [], []
    walk("C:", scan["tree"], "", 0, None, findings, unknowns)

    findings.sort(key=lambda x: -x["size"])
    unknowns.sort(key=lambda x: -x["size"])

    # 按安全等级汇总潜在可释放空间
    potential = {}
    for f_ in findings:
        potential.setdefault(f_["safety"], 0)
    # 只统计"叶子级"识别项会重复计数，这里简单按最外层同一规则首次出现统计
    seen_paths = []
    for f_ in findings:
        if any(f_["path"].startswith(p + "/") for p in seen_paths):
            continue
        seen_paths.append(f_["path"])
        potential[f_["safety"]] = potential.get(f_["safety"], 0) + f_["size"]

    result = {
        "meta": {k: scan[k] for k in ("target", "scanned_at", "elapsed_sec", "file_count",
                                      "disk_total", "disk_used", "disk_free",
                                      "scanned_size", "unscanned_size", "error_count")},
        "potential_by_safety": potential,
        "findings": findings,
        "unknowns": unknowns,
        "safety_label": {k: v[0] for k, v in SAFETY_LABEL.items()},
        "tree": scan["tree"],
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    print(f"[analyze] 识别出 {len(findings)} 个已知占用项，{len(unknowns)} 个待 AI 分析的未知大目录")
    for u in unknowns[:20]:
        print(f"  未识别: {u['path']}  {u['size']/1024**3:.1f} GB")


if __name__ == "__main__":
    main()
