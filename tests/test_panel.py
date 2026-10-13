import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from awg_panel.auth import AuthStore
from awg_panel.validate import expires_flag, parse_names, valid_client_name


class TestValidate(unittest.TestCase):
    def test_names(self):
        self.assertTrue(valid_client_name("my_phone-1"))
        self.assertFalse(valid_client_name("bad name"))
        self.assertFalse(valid_client_name("../x"))
        self.assertFalse(valid_client_name("a" * 64))

    def test_parse(self):
        ok, bad = parse_names("a, b;c\nd, a, bad name!")
        self.assertEqual(ok, ["a", "b", "c", "d", "bad"])
        self.assertEqual(bad, ["name!"])

    def test_expires_days_only(self):
        self.assertIsNone(expires_flag(""))
        self.assertIsNone(expires_flag(None))
        self.assertIsNone(expires_flag("0"))
        self.assertEqual(expires_flag("7"), "--expires=7d")
        with self.assertRaises(ValueError):
            expires_flag("7h")
        with self.assertRaises(ValueError):
            expires_flag("abc")
        with self.assertRaises(ValueError):
            expires_flag("99999")


class TestAuth(unittest.TestCase):
    def test_hash_verify(self):
        import tempfile
        h = AuthStore.hash_password("s3cret-password")
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write(h + "\n")
            path = f.name
        st = AuthStore(path, "/tmp/nonexistent-auth.log", 60)
        self.assertTrue(st.verify("s3cret-password"))
        self.assertFalse(st.verify("wrong"))

    def test_sessions(self):
        st = AuthStore("/nonexistent", "/tmp/nonexistent-auth.log", 60)
        s = st.create("1.2.3.4")
        self.assertIsNotNone(st.get(s.sid))
        st.destroy(s.sid)
        self.assertIsNone(st.get(s.sid))

    def test_rate_limit(self):
        st = AuthStore("/nonexistent", "/tmp/nonexistent-auth.log", 60)
        for _ in range(5):
            st.note_fail("9.9.9.9")
        self.assertTrue(st.blocked("9.9.9.9"))

    def test_rate_limit_gc(self):
        import time
        st = AuthStore("/nonexistent", "/tmp/nonexistent-auth.log", 60)
        st.fails["1.1.1.1"] = (2, 0.0, time.time() - 700)
        st._gc_fails()
        self.assertNotIn("1.1.1.1", st.fails)


class TestConfig(unittest.TestCase):
    def test_clamp(self):
        import tempfile
        from awg_panel.config import load_config
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nhost = \nport = 99999\nsession_ttl_min = 0\n")
            path = f.name
        cfg = load_config(path)
        self.assertEqual(cfg.host, "0.0.0.0")
        self.assertEqual(cfg.port, 8443)
        self.assertEqual(cfg.session_ttl_min, 1)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nsession_ttl_min = 9999\n")
            path2 = f.name
        self.assertEqual(load_config(path2).session_ttl_min, 1440)


class TestManage(unittest.TestCase):
    def test_parse_ok_flag(self):
        from awg_panel.manage import _parse_json_output
        r = _parse_json_output('{"ok": true, "x": 1}', 0, "")
        self.assertTrue(r.ok)
        self.assertEqual(r.data["x"], 1)
        r2 = _parse_json_output('{"ok": false}', 0, "e")
        self.assertFalse(r2.ok)
        r3 = _parse_json_output("not json", 0, "e")
        self.assertFalse(r3.ok)

    def test_add_argv_order_matches_sudoers(self):
        # Regression: --expires must sit between --yes and add,
        # and sudoers must allow that shape (see packaging/sudoers).
        import subprocess
        from unittest import mock
        from awg_panel import manage
        seen = {}

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, '{"ok": true}', "")

        with mock.patch.object(manage.subprocess, "run", fake_run):
            with mock.patch.object(manage, "_is_root", lambda: False):
                manage.cmd_add("/root/awg/manage_amneziawg.sh", ["alice"], "--expires=7d")
        cmd = seen["cmd"]
        # [..., "--json", "--no-color", "--yes", "--expires=7d", "add", "alice"]
        self.assertIn("--yes", cmd)
        yi = cmd.index("--yes")
        self.assertEqual(cmd[yi + 1], "--expires=7d")
        self.assertEqual(cmd[yi + 2], "add")
        sudoers = (Path(__file__).resolve().parents[1] / "packaging" / "sudoers").read_text()
        self.assertIn("--expires=* add *", sudoers)

    def test_sudoers_helper_enumerated(self):
        txt = (Path(__file__).resolve().parents[1] / "packaging" / "sudoers").read_text()
        self.assertNotIn("awg-panel-helper *", txt)
        for line in ("helper client-conf *", "helper server-pubkeys", "helper init-info"):
            self.assertIn(line, txt)


class TestSystemInfo(unittest.TestCase):
    def test_mem_info_malformed(self):
        from awg_panel import system_info
        orig = system_info._read
        system_info._read = lambda p: "MemTotal: broken\nMemFree:\n"
        try:
            out = system_info.mem_info()
            self.assertIn("used_kb", out)
        finally:
            system_info._read = orig


if __name__ == "__main__":
    unittest.main()
