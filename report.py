# -*- coding: utf-8 -*-
"""
report.py — 组装交互式 HTML 分析报告 (v2)

前端源码在 web/ 目录（index.html / app.css / app.js），本脚本把三个文件
内联拼接成单文件 output/report.html 并注入扫描数据——产物仍是零依赖单文件：
- 双击（file://）打开 = 只读报告
- 经 serve.py 打开 = 完整交互（清理篮/文件浏览器/AI/隔离区）
"""
import sys
import json
import os

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")


def build(data, ai):
    with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
        html = f.read()
    with open(os.path.join(WEB, "app.css"), encoding="utf-8") as f:
        css = f.read()
    with open(os.path.join(WEB, "app.js"), encoding="utf-8") as f:
        js = f.read()
    js = js.replace("__DATA__", json.dumps(data, ensure_ascii=False)) \
           .replace("__AI_NOTES__", json.dumps(ai, ensure_ascii=False))
    html = html.replace("/*__CSS__*/", css).replace("/*__JS__*/", js)
    return "<!doctype html>\n<html lang=\"zh-CN\">\n<body>\n" + html + "\n</body>\n</html>"


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

    out = build(data, ai)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"[report] 报告已生成: {out_file} ({os.path.getsize(out_file)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
