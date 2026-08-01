# -*- coding: utf-8 -*-
"""核心安全逻辑测试：判定引擎、winapp2 转换、清理白名单、隔离区往返。
运行: python -m unittest discover -s tests -v"""
import os
import sys
import json
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import knowledge          # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
