# -*- coding: utf-8 -*-
"""日志模块测试：落盘、会话文件、导出 zip、幂等。"""
import json
import logging
import os
import shutil
import tempfile
import unittest
import zipfile

from mk87lib import logsetup


class TestLogSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mk87-logtest-")
        self._old_env = os.environ.get("MK87_LOG_DIR")
        os.environ["MK87_LOG_DIR"] = self.tmp
        logsetup._installed = False  # 让 setup 重新初始化到临时目录
        self._old_handlers = list(logging.getLogger().handlers)

    def tearDown(self):
        root = logging.getLogger()
        for h in list(root.handlers):
            if h not in self._old_handlers:
                root.removeHandler(h)
                try:
                    h.close()
                except Exception:  # noqa: BLE001
                    pass
        for h in self._old_handlers:
            root.addHandler(h)
        logsetup._installed = False
        if self._old_env is None:
            os.environ.pop("MK87_LOG_DIR", None)
        else:
            os.environ["MK87_LOG_DIR"] = self._old_env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_logs_written_and_exported(self):
        st = logsetup.setup_logging(console=False, role="test")
        self.assertTrue(st["installed"])
        self.assertTrue(os.path.isdir(self.tmp))
        log = logging.getLogger("mk87.test")
        log.debug("hello debug")
        log.info("hello info")
        try:
            raise RuntimeError("boom-for-log")
        except RuntimeError:
            log.exception("captured exception")

        files = logsetup.list_logs()
        names = [f["name"] for f in files]
        self.assertTrue(any(n.startswith("session-") for n in names), names)
        self.assertIn("mk87.log", names)
        self.assertIn("errors.log", names)
        session = [f for f in files if f["name"].startswith("session-")][0]
        with open(session["path"], encoding="utf-8") as f:
            text = f.read()
        self.assertIn("hello debug", text)
        self.assertIn("captured exception", text)
        self.assertIn("RuntimeError: boom-for-log", text)
        # errors.log 只收 ERROR 及以上
        with open(os.path.join(self.tmp, "errors.log"), encoding="utf-8") as f:
            err = f.read()
        self.assertIn("boom-for-log", err)
        self.assertNotIn("hello info", err)

        res = logsetup.export_logs(extra={"note": "unit-test"})
        self.assertTrue(res["ok"])
        self.assertTrue(os.path.isfile(res["path"]))
        self.assertGreater(res["size"], 0)
        self.assertIn("downloadUrl", res)
        with zipfile.ZipFile(res["path"]) as z:
            names = z.namelist()
            self.assertIn("system-info.txt", names)
            self.assertIn("README.txt", names)
            self.assertTrue(any(n.startswith("session-") for n in names))
            info = json.loads(z.read("system-info.txt").decode("utf-8"))
            self.assertEqual(info["session"]["extra"]["note"], "unit-test")
            self.assertIn("version", info["session"])
        self.assertEqual(logsetup.find_export(res["name"]), res["path"])
        self.assertIsNone(logsetup.find_export("../evil.zip"))
        self.assertIsNone(logsetup.find_export("nope.zip"))

    def test_setup_idempotent(self):
        logsetup.setup_logging(console=False)
        n1 = len(logging.getLogger().handlers)
        logsetup.setup_logging(console=False)
        self.assertEqual(len(logging.getLogger().handlers), n1)
        self.assertEqual(len([f for f in logsetup.list_logs() if f["name"].startswith("session-")]), 1)

    def test_redact(self):
        self.assertEqual(logsetup.redact(b"\x01\x02"), "0102")
        self.assertLessEqual(len(logsetup.redact("ab" * 200, 10)), 20)


if __name__ == "__main__":
    unittest.main()
