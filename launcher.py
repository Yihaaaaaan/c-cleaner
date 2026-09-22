# -*- coding: utf-8 -*-
"""
launcher.py — 双击启动入口（被 "C盘清理.bat" 调用，也可单独 python launcher.py）

做四件双击场景下才需要的事：
  1. 服务已经在跑 → 直接开浏览器，不再起第二个（否则 8756 端口冲突报栈）；
  2. 从没扫过 → 直接进全盘扫描，不给菜单（新用户没得选）；
  3. 扫过 → 菜单 + 倒计时，什么都不按就打开上次的报告；
  4. 出错时窗口不要闪退，把原因留在屏幕上。
"""
import os
import sys
import time
import ctypes
import socket
import subprocess
import webbrowser

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
ANALYSIS = os.path.join(OUT, "analysis.json")
PORT = 8756
URL = "http://127.0.0.1:%d/" % PORT
WAIT = 10                      # 菜单倒计时秒数


def server_alive():
    """端口连得上 = 服务已经在跑（上一次双击留下的窗口还开着）。"""
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


def age_text(path):
    if not os.path.exists(path):
        return None
    sec = time.time() - os.path.getmtime(path)
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
    if sec < 3600:
        rel = "%d 分钟前" % (sec // 60)
    elif sec < 86400:
        rel = "%d 小时前" % (sec // 3600)
    else:
        rel = "%d 天前" % (sec // 86400)
    return "%s（%s）" % (stamp, rel)


def countdown_choice(seconds):
    """倒计时读一个键；超时返回 ''（= 用默认项）。非 Windows 环境直接用默认项。"""
    try:
        import msvcrt
    except ImportError:
        return ""
    end = time.time() + seconds
    while time.time() < end:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            print()
            return ch.strip().lower()
        left = int(end - time.time()) + 1
        print("\r  %d 秒后自动打开上次的报告，按键可选其他项 ... " % left, end="", flush=True)
        time.sleep(0.2)
    print()
    return ""


def serve():
    """前台跑服务：这个窗口就是服务本体，关掉即停止。"""
    print("\n正在启动报告服务 ... 浏览器会自动打开")
    print("完事后关掉这个窗口（或按 Ctrl+C）即可停止服务\n")
    subprocess.call([sys.executable, os.path.join(HERE, "serve.py")], cwd=HERE)


def rescan(target):
    print("\n开始扫描 %s ，约需 1 分钟，请勿关闭窗口 ...\n" % target)
    r = subprocess.call([sys.executable, os.path.join(HERE, "main.py"),
                         target, "--static", "--no-open"], cwd=HERE)
    if r != 0:
        raise SystemExit("扫描失败（退出码 %d），上面有错误详情" % r)
    serve()


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


def _guid(s):
    g = _GUID()
    ctypes.oledll.ole32.CLSIDFromString(s, ctypes.byref(g))
    return g


def write_lnk(lnk, target, workdir="", icon="", desc="", args=""):
    """用 ctypes 直调 IShellLinkW 写 .lnk。

    不走 WScript.Shell：路径里带中文时它会抛
    "Value does not fall within the expected range"（本项目目录就带中文），
    而且 8.3 短名在很多卷上是关的，绕不过去。IShellLinkW 是原生 Unicode。
    """
    from ctypes import byref, POINTER, c_void_p, c_wchar_p, c_int, WINFUNCTYPE

    ole32 = ctypes.windll.ole32
    CLSID_ShellLink = _guid("{00021401-0000-0000-C000-000000000046}")
    IID_IShellLinkW = _guid("{000214F9-0000-0000-C000-000000000046}")
    IID_IPersistFile = _guid("{0000010B-0000-0000-C000-000000000046}")

    ole32.CoInitialize(None)
    obj = c_void_p()
    hr = ole32.CoCreateInstance(byref(CLSID_ShellLink), None, 1,   # INPROC_SERVER
                                byref(IID_IShellLinkW), byref(obj))
    if hr < 0:
        raise OSError("CoCreateInstance 失败 0x%08X" % (hr & 0xFFFFFFFF))

    def method(ptr, index, *argtypes):
        vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p)))[0]
        return WINFUNCTYPE(c_int, c_void_p, *argtypes)(vtbl[index])

    def check(hr_, what):
        if hr_ < 0:
            raise OSError("%s 失败 0x%08X" % (what, hr_ & 0xFFFFFFFF))

    try:
        check(method(obj, 20, c_wchar_p)(obj, target), "SetPath")
        if args:
            check(method(obj, 11, c_wchar_p)(obj, args), "SetArguments")
        if workdir:
            check(method(obj, 9, c_wchar_p)(obj, workdir), "SetWorkingDirectory")
        if desc:
            check(method(obj, 7, c_wchar_p)(obj, desc), "SetDescription")
        if icon:
            path, _, idx = icon.rpartition(",")
            check(method(obj, 17, c_wchar_p, c_int)(obj, path, int(idx)),
                  "SetIconLocation")
        pf = c_void_p()
        check(method(obj, 0, c_void_p, c_void_p)(obj, byref(IID_IPersistFile),
                                                 byref(pf)), "QueryInterface")
        try:
            check(method(pf, 6, c_wchar_p, c_int)(pf, lnk, 1), "IPersistFile::Save")
        finally:
            method(pf, 2)(pf)                       # Release
    finally:
        method(obj, 2)(obj)                         # Release


def windowless_python():
    """找一个不带控制台的解释器：pyw.exe 或 pythonw.exe，都没有则 None。

    快捷方式直指它，可以完全没有黑窗一闪（走 .bat 的话 cmd 窗口必闪一下）。
    """
    for c in (os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "pyw.exe"),
              os.path.join(os.path.dirname(sys.executable or ""), "pythonw.exe")):
        if os.path.isfile(c):
            return c
    return None


def make_shortcut():
    """在桌面放一个快捷方式，指向桌面应用入口 desktop.py。"""
    app = os.path.join(HERE, "desktop.py")
    bat = os.path.join(HERE, "C盘清理.bat")
    if not os.path.isfile(app):
        raise SystemExit("找不到 %s" % app)
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        raise SystemExit("找不到桌面目录：%s" % desktop)
    lnk = os.path.join(desktop, "C盘清理.lnk")
    icon = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                        "System32", "cleanmgr.exe") + ",0"
    pyw = windowless_python()
    if pyw:
        write_lnk(lnk, pyw, HERE, icon, "C盘清理分析器 - 扫描并清理 C 盘",
                  args='"%s"' % app)
    else:
        if not os.path.isfile(bat):
            raise SystemExit("找不到 %s" % bat)
        write_lnk(lnk, bat, HERE, icon, "C盘清理分析器 - 扫描并清理 C 盘")
    if not os.path.isfile(lnk):                     # 别信"没报错"，看文件在不在
        raise SystemExit("快捷方式没写成：%s" % lnk)
    print("桌面快捷方式已创建：%s" % lnk)
    print("以后双击桌面上的「C盘清理」即可。")


def main():
    if "--shortcut" in sys.argv:
        make_shortcut()
        return

    print("=" * 52)
    print("  C 盘清理分析器")
    print("=" * 52)

    if server_alive():
        print("\n服务已经在运行了，直接打开页面：%s" % URL)
        webbrowser.open(URL)
        return

    stamp = age_text(ANALYSIS)
    if not stamp:
        print("\n还没有扫描记录，先做一次全盘扫描。")
        rescan("C:\\")
        return

    print("\n上次扫描：%s\n" % stamp)
    print("  [1] 打开上次的报告          （默认）")
    print("  [2] 重新扫描 C 盘")
    print("  [3] 扫描其他盘")
    print("  [Q] 退出\n")

    c = countdown_choice(WAIT)
    if c == "q":
        return
    if c == "2":
        rescan("C:\\")
    elif c == "3":
        d = input("盘符（例如 D）: ").strip().rstrip(":\\/ ")
        if not d:
            raise SystemExit("没输入盘符，已退出")
        rescan(d.upper() + ":\\")
    else:
        serve()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止")
    except SystemExit as e:
        if e.code not in (0, None):
            print("\n[错误] %s" % e.code)
            input("\n按回车关闭 ...")
            sys.exit(1)
    except Exception as e:
        print("\n[错误] %s: %s" % (e.__class__.__name__, e))
        input("\n按回车关闭 ...")
        sys.exit(1)
