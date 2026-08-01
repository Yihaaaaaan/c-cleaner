# -*- coding: utf-8 -*-
"""
main.py — C盘清理分析 一键入口

用法:
    python main.py                    # 扫描 C 盘 → 分析 → 生成报告并打开
    python main.py D:\\               # 扫描其他盘
    python main.py --no-open          # 不自动打开报告
    python main.py --ai               # 对知识库未识别的大目录调用 Claude CLI 做 AI 分析
                                      # （需要已安装 claude 命令行；不加此参数则沿用已有的 ai_notes.json）
"""
import os
import sys
import json
import subprocess

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")

AI_PROMPT = """你是 Windows 磁盘清理专家。下面是磁盘扫描后知识库未能识别的大目录列表（JSON）。
请逐一分析每个目录：它是什么软件/系统产生的、里面装什么、能不能删、推荐清理方法。
只输出 JSON，格式如下（safety 取值: safe/caution/danger/keep/user）：
{"notes": [{"path": "...", "title": "...", "safety": "...", "desc": "...", "action": "..."}]}

未识别目录列表：
"""


def run(args_list):
    subprocess.run([sys.executable] + args_list, cwd=HERE, check=True)


def ai_analyze():
    """调用 claude CLI 分析未识别目录，生成/更新 output/ai_notes.json"""
    with open(os.path.join(OUT, "analysis.json"), encoding="utf-8") as f:
        unknowns = json.load(f)["unknowns"]
    if not unknowns:
        print("[ai] 没有未识别的大目录，跳过 AI 分析")
        return
    prompt = AI_PROMPT + json.dumps(unknowns, ensure_ascii=False, indent=1)
    print(f"[ai] 正在调用 Claude 分析 {len(unknowns)} 个未识别目录 ...")
    r = subprocess.run(["claude", "-p", prompt, "--output-format", "text"],
                       capture_output=True, text=True, encoding="utf-8", shell=True)
    txt = (r.stdout or "").strip()
    # 提取 JSON（容忍 ```json 包裹）
    if "```" in txt:
        txt = txt.split("```")[1]
        if txt.startswith("json"):
            txt = txt[4:]
    try:
        notes = json.loads(txt)
        assert "notes" in notes
    except Exception:
        print("[ai] Claude 输出无法解析为 JSON，已跳过（沿用现有 ai_notes.json）")
        return
    with open(os.path.join(OUT, "ai_notes.json"), "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=1)
    print(f"[ai] AI 分析完成，共 {len(notes['notes'])} 条")


def main():
    args = [a for a in sys.argv[1:]]
    target = next((a for a in args if not a.startswith("--")), "C:\\")
    os.makedirs(OUT, exist_ok=True)

    run(["scanner.py", target, os.path.join(OUT, "scan_result.json")])
    run(["analyze.py", os.path.join(OUT, "scan_result.json"),
         os.path.join(OUT, "analysis.json")])
    if "--ai" in args:
        ai_analyze()
    run(["report.py", os.path.join(OUT, "analysis.json"),
         os.path.join(OUT, "ai_notes.json"), os.path.join(OUT, "report.html")])

    report = os.path.join(OUT, "report.html")
    print(f"\n完成！报告: {report}")
    if "--static" in args:
        if "--no-open" not in args:
            os.startfile(report)
    else:
        # 启动本地服务（报告页面才能提交清理 / AI 深挖），Ctrl+C 停止
        serve_args = [sys.executable, os.path.join(HERE, "serve.py")]
        if "--no-open" in args:
            serve_args.append("--no-open")
        subprocess.run(serve_args, cwd=HERE)


if __name__ == "__main__":
    main()
