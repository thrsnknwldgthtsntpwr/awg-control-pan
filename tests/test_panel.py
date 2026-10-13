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
        # Portable sudoers: single trailing `*` after --yes (embedded wildcards
        # like --expires=* are rejected by sudo-rs). Must cover expires order.
        rules = [l for l in sudoers.splitlines() if l.strip() and not l.strip().startswith("#")]
        self.assertTrue(any(l.rstrip().endswith("--yes *") for l in rules))
        self.assertFalse(any("--expires=" in l for l in rules))

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


class TestPackaging(unittest.TestCase):
    def test_deb_files_root_owned(self):
        # Regression: 0.1.1 built as uid 1001 shipped sudoers owned by 1001,
        # which breaks ALL sudo on target ("should be 0").
        build = (Path(__file__).resolve().parents[1] / "build_deb.sh").read_text()
        self.assertIn("root-owner-group", build)
        self.assertIn("chown -R 0:0", build)

    def test_postinst_heals_sudoers_owner(self):
        postinst = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "postinst").read_text()
        self.assertIn("chown root:root /etc/sudoers.d/awg-panel", postinst)
        # chown must run before the visudo check, otherwise a broken
        # owner still fails validation on upgrade.
        self.assertLess(
            postinst.index("chown root:root /etc/sudoers.d/awg-panel"),
            postinst.index("visudo -c"),
        )
        self.assertIn("chmod 440 /etc/sudoers.d/awg-panel", postinst)

    def test_postinst_tls_key_group_readable(self):
        # Regression 0.1.2: key.pem was 600 root:awgpanel -> service as
        # User=awgpanel got TLS load Permission denied + restart-loop.
        # Key must be 640 root:awgpanel, healed on every upgrade (not only create).
        postinst = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "postinst").read_text()
        self.assertIn("chmod 640 /etc/awg-panel/key.pem", postinst)
        self.assertNotIn("chmod 600 /etc/awg-panel/key.pem", postinst)
        self.assertIn("chown root:awgpanel /etc/awg-panel/key.pem", postinst)

    def test_postinst_prints_next_steps(self):
        postinst = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "postinst").read_text()
        for marker in (
            "/etc/awg-panel/config.ini",
            "systemctl restart awg-panel",
            "awg-panel-set-password",
            "https://<IP",
            "/root/.awg-panel-initial-password",
        ):
            self.assertIn(marker, postinst)


if __name__ == "__main__":
    unittest.main()
