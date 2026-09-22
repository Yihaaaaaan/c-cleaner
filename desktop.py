# -*- coding: utf-8 -*-
"""
desktop.py — 桌面应用模式：自己的窗口，没有地址栏和标签页。

和 launcher.py 的区别：launcher 是控制台菜单 + 普通浏览器标签页；
desktop 是双击就出一个独立窗口，像装了个软件。

实现方式是 Chromium 的 --app 模式（Edge 或 Chrome，Win10/11 自带 Edge），
配合独立 --user-data-dir：
  * 独立 profile 才能拿到独立进程，窗口关掉我们才知道该收服务；
    不加的话新窗口会挂到你已经开着的浏览器上，进程秒退，服务就成了僵尸；
  * 也不会污染你日常浏览器的历史、插件、登录态。
找不到 Chromium 就退回普通浏览器，功能一样，只是多个地址栏。

不用 pywebview/Electron：本项目坚持零依赖，且 WebView2 运行时不保证装了。
"""
import os
import sys
import time
import socket
import threading
import subprocess
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.join(HERE, "output", "analysis.json")
PORT = 8756
URL = "http://127.0.0.1:%d/" % PORT
PROFILE = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "c-cleaner", "appwin")
CREATE_NO_WINDOW = 0x08000000      # 子进程别弹黑窗
BOOT_TIMEOUT = 30                  # 等服务起来的秒数


def server_alive():
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


def find_chromium():
    """返回 Edge/Chrome 的 exe 路径，没有则 None。Win10/11 自带 Edge，基本必中。"""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def pythonw():
    """优先用 pythonw.exe 跑后台服务：控制台版会留一个黑窗在任务栏。"""
    exe = sys.executable or ""
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.isfile(cand) else exe


def start_server():
    """后台起 serve.py，返回 Popen。调用方负责在窗口关闭后收掉它。"""
    return subprocess.Popen(
        [pythonw(), os.path.join(HERE, "serve.py"), "--no-open"],
        cwd=HERE, creationflags=CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_alive(timeout=BOOT_TIMEOUT):
    end = time.time() + timeout
    while time.time() < end:
        if server_alive():
            return True
        time.sleep(0.3)
    return False


def run_scan(target, on_line=None):
    """跑一次扫描，逐行回调进度。返回退出码。"""
    p = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "main.py"), target, "--static", "--no-open"],
        cwd=HERE, creationflags=CREATE_NO_WINDOW,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1)
    for line in p.stdout:
        line = line.rstrip()
        if line and on_line:
            on_line(line)
    return p.wait()


def open_window(exe):
    """开 app 窗口。exe 为 None 时退回普通浏览器（返回 None 表示没进程可等）。"""
    if not exe:
        webbrowser.open(URL)
        return None
    os.makedirs(PROFILE, exist_ok=True)
    return subprocess.Popen([
        exe,
        "--app=" + URL,
        "--user-data-dir=" + PROFILE,
        "--window-size=1440,900",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate,AutofillServerCommunication",
    ], creationflags=CREATE_NO_WINDOW)


# ---------- 启动画面（tkinter，标准库自带；缺了就退回控制台打印） ----------
class Splash(object):
    """扫描要几十秒，没有画面用户会以为双击没反应，所以必须有个东西顶着。"""

    def __init__(self):
        self.tk = None
        self.root = None
        try:
            import tkinter as tk
        except ImportError:
            return
        self.tk = tk
        self.root = tk.Tk()
        self.root.title("C盘清理")
        self.root.geometry("460x150")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e24")
        self.root.attributes("-topmost", True)
        try:
            self.root.eval("tk::PlaceWindow . center")
        except Exception:
            pass
        self.title = tk.Label(self.root, text="C 盘清理分析器", fg="#ffffff",
                              bg="#1e1e24", font=("Microsoft YaHei UI", 14, "bold"))
        self.title.pack(pady=(28, 6))
        self.msg = tk.Label(self.root, text="启动中 ...", fg="#a8a8b3", bg="#1e1e24",
                            font=("Microsoft YaHei UI", 9), wraplength=420)
        self.msg.pack()

    def status(self, text):
        if not self.root:
            print(text)
            return
        self.msg.config(text=text[:120])
        self.root.update()

    def pump(self):
        if self.root:
            self.root.update()

    def close(self):
        if self.root:
            self.root.destroy()
            self.root = None


def main():
    splash = Splash()
    # msg 是线程间唯一的通道：worker 只写字符串，主线程才碰 tk。
    # tkinter 不是线程安全的，从 worker 里直接改 Label 会当场抛异常，
    # 结果就是双击后只弹一个“启动失败”，服务根本没起来。
    state = {"err": None, "proc": None, "ours": None, "msg": "启动中 ..."}

    def work():
        try:
            if not server_alive():
                if not os.path.exists(ANALYSIS):
                    state["msg"] = "第一次运行，正在扫描 C 盘（约 1 分钟）..."
                    code = run_scan("C:\\", lambda ln: state.__setitem__("msg", ln))
                    if code != 0:
                        state["err"] = "扫描失败，退出码 %d" % code
                        return
                state["msg"] = "正在启动本地服务 ..."
                state["ours"] = start_server()
                if not wait_alive():
                    state["err"] = ("服务没能在 %d 秒内启动。\n"
                                    "试试在命令行跑 python serve.py 看具体报错。"
                                    % BOOT_TIMEOUT)
                    return
            state["msg"] = "正在打开窗口 ..."
            state["proc"] = open_window(find_chromium())
        except Exception:
            import traceback
            state["err"] = traceback.format_exc()      # 双击场景没控制台，栈得带进弹窗

    t = threading.Thread(target=work)
    t.daemon = True
    t.start()
    shown = None
    while t.is_alive():                 # 主线程只管画面
        if state["msg"] != shown:
            shown = state["msg"]
            splash.status(shown)
        splash.pump()
        time.sleep(0.05)

    if state["err"]:
        splash.close()
        fail(state["err"])
        return

    time.sleep(1.2)                     # 让窗口先出来，splash 再消失，避免闪一下空屏
    splash.close()

    proc = state["proc"]
    if proc:
        proc.wait()                     # 窗口关了才往下走
    ours = state["ours"]
    if ours and proc:                   # 服务是我们起的，且确实等到了窗口关闭
        ours.terminate()


def fail(msg):
    """报错必须看得见：双击场景下没有控制台，得弹窗。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "C盘清理 - 启动失败", 0x10)
    except Exception:
        print(msg)
        try:
            input("按回车关闭 ...")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
