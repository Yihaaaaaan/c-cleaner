# -*- coding: utf-8 -*-
"""核心安全逻辑测试：判定引擎、winapp2 转换、清理白名单、隔离区往返。
运行: python -m unittest discover -s tests -v"""
import os
import sys
import json
import shutil
import stat
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import knowledge          # noqa: E402
import launcher           # noqa: E402
import serve              # noqa: E402
import winapp2 as w2      # noqa: E402

USER = os.environ.get("USERNAME") or os.path.basename(os.path.expanduser("~"))


class TestKnowledge(unittest.TestCase):
    """知识库匹配：用户硬规则绝不被覆盖。"""

    def test_wechat_chat_protected(self):
        r = knowledge.match_rule(f"Users/{USER}/Documents/WeChat Files")
        self.assertIsNotNone(r)
        if knowledge.USER_PROTECTED:            # 配了个人保护规则 → keep
            self.assertEqual(r["safety"], "keep")
        else:                                    # 干净 clone → 至少是"自行决定"，绝不能是 safe
            self.assertIn(r["safety"], ("user", "keep"))

    def test_user_protected_rules_are_keep(self):
        for r in knowledge.USER_PROTECTED:
            self.assertEqual(r["safety"], "keep")
            hit = knowledge.match_rule(r["pattern"].replace("<user>", USER))
            self.assertEqual(hit["safety"], "keep", r["pattern"])

    def test_temp_safe(self):
        r = knowledge.match_rule(f"Users/{USER}/AppData/Local/Temp")
        self.assertEqual(r["safety"], "safe")

    def test_winsxs_danger(self):
        r = knowledge.match_rule("Windows/WinSxS")
        self.assertEqual(r["safety"], "danger")


class TestJudgeEntry(unittest.TestCase):
    """逐项判定：扩展名规则、祖先继承。"""

    def test_dll_keep(self):
        s, _ = serve.judge_entry("Program Files/Foo/bar.dll", "bar.dll", False, {})
        self.assertEqual(s, "keep")

    def test_log_safe(self):
        s, _ = serve.judge_entry("SomeApp/x.log", "x.log", False, {})
        self.assertEqual(s, "safe")

    def test_cache_dir_children_inherit_safe(self):
        s, why = serve.judge_entry(
            f"Users/{USER}/AppData/Roaming/FooApp/Cache/sub", "sub", True, {})
        self.assertEqual(s, "safe")
        self.assertIn("Cache", why)


class TestWinapp2(unittest.TestCase):
    """winapp2 转换的安全映射。"""

    def test_full_content_safe_but_privacy_user(self):
        text = ("[Foo Cache *]\nFileKey1=%LocalAppData%\\FooCacheTestDir|*|RECURSE\n"
                "[Bar History *]\nFileKey1=%LocalAppData%\\BarHistTestDir|*|RECURSE\n")
        rules, active = w2.convert(w2.parse_ini(text))
        self.assertEqual(active, 2)
        by = {r["pattern"].rsplit("/", 1)[-1].lower(): r for r in rules}
        self.assertEqual(by["foocachetestdir"]["safety"], "safe")     # 纯缓存 → safe
        self.assertEqual(by["barhisttestdir"]["safety"], "user")      # 隐私类 → user

    def test_partial_filekey_not_safe(self):
        text = "[Foo Logs *]\nFileKey1=%LocalAppData%\\FooPartialDir|*.log\n"
        rules, _ = w2.convert(w2.parse_ini(text))
        self.assertEqual(rules[0]["safety"], "caution")   # 只删部分文件 → 不能整目录 safe

    def test_warning_forces_caution(self):
        text = ("[Foo Risky *]\nWarning=This may break things\n"
                "FileKey1=%LocalAppData%\\FooRiskyDir|*|RECURSE\n")
        rules, _ = w2.convert(w2.parse_ini(text))
        self.assertEqual(rules[0]["safety"], "caution")


class TestCleanSafety(unittest.TestCase):
    """清理接口的安全闸门。"""

    def test_non_whitelist_rejected(self):
        res = serve.api_clean(["C:/Windows/System32"])
        self.assertEqual(res["results"][0]["status"], "拒绝")

    def test_keep_entry_rejected(self):
        res = serve.api_clean_items("C:/Windows", ["System32"])
        self.assertEqual(res["results"][0]["status"], "拒绝")

    def test_path_traversal_rejected(self):
        res = serve.api_clean_items("C:/Users", ["../evil"])
        self.assertEqual(res["results"][0]["status"], "拒绝")
        res2 = serve.api_clean_items("C:/Users", ["..\\evil"])
        self.assertEqual(res2["results"][0]["status"], "拒绝")

    def test_wechat_clean_paths_rejected(self):
        res = serve.api_clean_paths([f"C:/Users/{USER}/Documents/WeChat Files"])
        self.assertIn(res["results"][0]["status"], ("拒绝", "跳过"))  # 存在则拒绝，不存在则跳过


class TestQuarantineRoundtrip(unittest.TestCase):
    """隔离 → manifest → 还原 全链路。"""

    def setUp(self):
        self.scratch = os.path.join(os.environ["LOCALAPPDATA"], "Temp", "cc_unittest_dir")
        shutil.rmtree(self.scratch, ignore_errors=True)
        os.makedirs(self.scratch)
        with open(os.path.join(self.scratch, "a.log"), "w") as f:
            f.write("x" * 1000)

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)

    def test_clean_manifest_restore(self):
        base = self.scratch.replace("\\", "/")
        res = serve.api_clean_items(base, ["a.log"])
        self.assertEqual(res["results"][0]["status"], "完成")
        qdir = res["quarantine"]
        batch = os.path.basename(os.path.dirname(qdir))
        mf = os.path.join(os.path.dirname(qdir), "manifest.json")
        self.assertTrue(os.path.isfile(mf), "manifest 必须存在")
        self.assertFalse(os.path.exists(os.path.join(self.scratch, "a.log")))
        rr = serve.api_quarantine_restore(batch)
        self.assertGreaterEqual(rr["restored"], 1)
        self.assertTrue(os.path.exists(os.path.join(self.scratch, "a.log")), "文件应回原位")


class TestSuspicion(unittest.TestCase):
    """隔离区复检的不可再生特征。"""

    def test_docx_suspicious(self):
        self.assertIsNotNone(serve.check_file_suspicion("简历.docx", 1000))

    def test_kdbx_suspicious(self):
        self.assertIsNotNone(serve.check_file_suspicion("pass.kdbx", 100))

    def test_log_not_suspicious(self):
        self.assertIsNone(serve.check_file_suspicion("debug.log", 10**9))

    def test_small_media_ok_big_media_flagged(self):
        self.assertIsNone(serve.check_file_suspicion("thumb.jpg", 100 * 1024))
        self.assertIsNotNone(serve.check_file_suspicion("photo.jpg", 5 * 1024 * 1024))


class TestForceRmtree(unittest.TestCase):
    """只读文件（git 的 .pack/.idx 就是只读的）必须能删掉，且删不掉时不许谎报。"""

    def setUp(self):
        self.scratch = os.path.join(os.environ["LOCALAPPDATA"], "Temp", "cc_unittest_ro")
        shutil.rmtree(self.scratch, ignore_errors=True)
        os.makedirs(os.path.join(self.scratch, ".git", "objects", "pack"))
        self.pack = os.path.join(self.scratch, ".git", "objects", "pack", "p.pack")
        with open(self.pack, "w") as f:
            f.write("x" * 1000)
        os.chmod(self.pack, stat.S_IREAD)      # git 就是这么留的

    def tearDown(self):
        for root, _dirs, files in os.walk(self.scratch):
            for fn in files:
                try:
                    os.chmod(os.path.join(root, fn), stat.S_IWRITE)
                except OSError:
                    pass
        shutil.rmtree(self.scratch, ignore_errors=True)

    def test_readonly_file_is_removed(self):
        failed = serve.force_rmtree(self.scratch)
        self.assertEqual(failed, [], "只读文件应被清除只读位后删掉")
        self.assertFalse(os.path.exists(self.scratch))

    def test_plain_rmtree_would_have_failed(self):
        """回归锚点：老写法 ignore_errors=True 会静默残留——正是这个 bug。"""
        shutil.rmtree(self.scratch, ignore_errors=True)
        self.assertTrue(os.path.exists(self.pack), "只读文件不该被静默删掉（证明旧写法有残留）")

    def test_force_delete_readonly_file(self):
        serve.force_delete(self.pack)
        self.assertFalse(os.path.exists(self.pack))

    def test_empty_reports_real_freed_bytes(self):
        """api_quarantine('empty') 报的 freed_bytes 必须是实测释放量。"""
        qroot = serve.quarantine_roots()[0] if serve.quarantine_roots() else None
        if not qroot:
            self.skipTest("本机没有隔离区")
        batch = "20200101_000000"          # 假批次，测完即删
        bdir = os.path.join(qroot, batch)
        os.makedirs(bdir, exist_ok=True)
        try:
            p = os.path.join(bdir, "ro.pack")
            with open(p, "w") as f:
                f.write("y" * 4096)
            os.chmod(p, stat.S_IREAD)
            r = serve.api_quarantine("empty", batch)
            self.assertEqual(r.get("failed_count", 0), 0)
            self.assertGreaterEqual(r["freed_bytes"], 4096)
            self.assertFalse(os.path.exists(bdir))
        finally:
            for root, _d, files in os.walk(bdir):
                for fn in files:
                    try:
                        os.chmod(os.path.join(root, fn), stat.S_IWRITE)
                    except OSError:
                        pass
            shutil.rmtree(bdir, ignore_errors=True)


class TestLauncher(unittest.TestCase):
    """双击入口：端口探活、扫描时间显示、快捷方式写入。"""

    def setUp(self):
        self.tmp = os.path.join(os.environ["LOCALAPPDATA"], "Temp", "cc_unittest_lnk")
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.makedirs(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_port_matches_serve(self):
        """launcher 探的端口必须和 serve 实际监听的是同一个。"""
        self.assertEqual(launcher.PORT, serve.PORT)

    def test_server_alive_false_when_nothing_listening(self):
        import socket as _s
        sock = _s.socket()
        sock.bind(("127.0.0.1", 0))          # 借一个确定没人用的端口
        free_port = sock.getsockname()[1]
        sock.close()
        old, launcher.PORT = launcher.PORT, free_port
        try:
            self.assertFalse(launcher.server_alive())
        finally:
            launcher.PORT = old

    def test_age_text_missing_file(self):
        self.assertIsNone(launcher.age_text(os.path.join(self.tmp, "nope.json")))

    def test_age_text_fresh_file(self):
        p = os.path.join(self.tmp, "a.json")
        open(p, "w").close()
        self.assertIn("分钟前", launcher.age_text(p))

    def test_write_lnk_handles_chinese_path(self):
        """项目目录本身带中文；WScript.Shell 在这种路径上会报
        'Value does not fall within the expected range'，所以必须走 IShellLinkW。"""
        cdir = os.path.join(self.tmp, "中文目录")
        os.makedirs(cdir)
        target = os.path.join(cdir, "启动.bat")
        with open(target, "w") as f:
            f.write("@echo off\n")
        lnk = os.path.join(self.tmp, "测试快捷方式.lnk")
        launcher.write_lnk(lnk, target, cdir, desc="unittest")
        self.assertTrue(os.path.isfile(lnk), "带中文路径的快捷方式必须能写成")
        self.assertGreater(os.path.getsize(lnk), 0)

    def test_bat_entry_exists_and_is_ascii(self):
        """.bat 内容必须是纯 ASCII：非 UTF-8 代码页下中文会被 cmd 吃成乱码。"""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("C盘清理.bat", "创建桌面快捷方式.bat"):
            p = os.path.join(root, name)
            self.assertTrue(os.path.isfile(p), name + " 必须存在")
            with open(p, "rb") as f:
                body = f.read()
            try:
                body.decode("ascii")
            except UnicodeDecodeError:
                self.fail(name + " 含非 ASCII 字符")


if __name__ == "__main__":
    unittest.main()
