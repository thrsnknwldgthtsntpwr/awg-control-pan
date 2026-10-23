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
    def test_session_expiry_remains_enforced(self):
        import time
        st = AuthStore({"admin": "pw"}, ttl_sec=60, max_lifetime_sec=120)
        expired = st.create("127.0.0.1", "admin")
        expired.expires = time.time() - 1
        self.assertIsNone(st.get(expired.sid))
        absolute = st.create("127.0.0.1", "admin")
        absolute.created = time.time() - 121
        absolute.expires = time.time() + 60
        self.assertIsNone(st.get(absolute.sid))

    def test_verify_config_credentials(self):
        st = AuthStore({"admin": "s3cret-password"}, "/tmp/nonexistent-auth.log", 60)
        self.assertTrue(st.verify("admin", "s3cret-password"))
        self.assertFalse(st.verify("admin", "wrong"))
        self.assertFalse(st.verify("other", "s3cret-password"))
        self.assertFalse(st.verify("", ""))

    def test_verify_multi_no_cross_password(self):
        st = AuthStore({"user1": "password1", "user2": "password2"},
                       "/tmp/nonexistent-auth.log", 60)
        self.assertTrue(st.verify("user1", "password1"))
        self.assertTrue(st.verify("user2", "password2"))
        # пароль от одного не подходит другому
        self.assertFalse(st.verify("user1", "password2"))
        self.assertFalse(st.verify("user2", "password1"))
        self.assertFalse(st.verify("nosuch", "password1"))

    def test_sessions(self):
        st = AuthStore({"admin": "pw"}, "/tmp/nonexistent-auth.log", 60)
        s = st.create("1.2.3.4", "admin")
        self.assertIsNotNone(st.get(s.sid))
        st.destroy(s.sid)
        self.assertIsNone(st.get(s.sid))

    def test_session_stores_username(self):
        st = AuthStore({"user1": "password1"}, "/tmp/nonexistent-auth.log", 60)
        s = st.create("1.2.3.4", "user1")
        got = st.get(s.sid)
        self.assertIsNotNone(got)
        self.assertEqual(got.username, "user1")

    def test_rate_limit(self):
        st = AuthStore({"admin": "pw"}, "/tmp/nonexistent-auth.log", 60)
        for _ in range(5):
            st.note_fail("9.9.9.9")
        self.assertTrue(st.blocked("9.9.9.9"))

    def test_rate_limit_custom(self):
        import time
        st = AuthStore({"admin": "pw"}, "/tmp/nonexistent-auth.log", 60, 3, 120)
        st.note_fail("9.9.9.9")
        st.note_fail("9.9.9.9")
        self.assertFalse(st.blocked("9.9.9.9"))
        st.note_fail("9.9.9.9")
        self.assertTrue(st.blocked("9.9.9.9"))
        _c, until, _l = st.fails["9.9.9.9"]
        self.assertGreater(until, time.time() + 100)

    def test_rate_limit_gc(self):
        import time
        st = AuthStore({"admin": "pw"}, "/tmp/nonexistent-auth.log", 60)
        st.fails["1.1.1.1"] = (2, 0.0, time.time() - 700)
        st._gc_fails()
        self.assertNotIn("1.1.1.1", st.fails)


class TestConfig(unittest.TestCase):
    def test_obsolete_paths_are_ignored(self):
        import tempfile
        from awg_panel.config import load_config
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            path.write_text("[server]\nawg_dir=/unused\nserver_conf=/unused.conf\n"
                            "[users]\nuser.1=admin\npassword.1=pw\n")
            cfg = load_config(str(path))
        self.assertEqual(cfg.manage_script, "/root/awg/manage_amneziawg.sh")
        self.assertEqual(cfg.helper, "/usr/sbin/awg-panel-helper")
        self.assertFalse(hasattr(cfg, "awg_dir"))
        self.assertFalse(hasattr(cfg, "server_conf"))

    def test_clamp(self):
        import tempfile
        from awg_panel.config import load_config
        users = "[users]\nuser.1 = admin\npassword.1 = admin\n"
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nhost = \nport = 99999\nsession_ttl_min = 0\n" + users)
            path = f.name
        cfg = load_config(path)
        self.assertEqual(cfg.host, "0.0.0.0")
        self.assertEqual(cfg.port, 8443)
        self.assertEqual(cfg.session_ttl_min, 1)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nsession_ttl_min = 9999\n" + users)
            path2 = f.name
        self.assertEqual(load_config(path2).session_ttl_min, 1440)

    def test_users_numbered(self):
        import tempfile
        from awg_panel.config import load_config
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nport = 8443\n"
                    "[users]\nuser.1 = user1\npassword.1 = password1\n"
                    "user.2 = user2\npassword.2 = password2\n")
            path = f.name
        cfg = load_config(path)
        self.assertEqual(cfg.users, {"user1": "password1", "user2": "password2"})

    def test_users_required_fail_closed(self):
        import tempfile
        from awg_panel.config import load_config
        # нет секции [users] -> отказ старта (обратной совместимости нет)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nport = 8443\n")
            path = f.name
        with self.assertRaises(ValueError):
            load_config(path)
        # старые ключи webusername/webpassword игнорируются и не спасают
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nwebusername = solo\nwebpassword = s3cret\n")
            path2 = f.name
        with self.assertRaises(ValueError):
            load_config(path2)
        # нет файла -> отказ старта
        with self.assertRaises(ValueError):
            load_config("/tmp/awg-panel-no-such-config-12345.ini")

    def test_users_errors_fail_closed(self):
        import tempfile
        from awg_panel.config import load_config
        cases = [
            # password.2 без user.2
            "[users]\nuser.1 = a\npassword.1 = p1\npassword.2 = p2\n",
            # user.2 без password.2
            "[users]\nuser.1 = a\npassword.1 = p1\nuser.2 = b\n",
            # дубль логина
            "[users]\nuser.1 = same\npassword.1 = p1\nuser.2 = same\npassword.2 = p2\n",
            # плохой логин
            "[users]\nuser.1 = bad name!\npassword.1 = p1\n",
            # пустой пароль
            "[users]\nuser.1 = a\npassword.1 = \n",
            # неизвестный ключ
            "[users]\nuser.1 = a\npassword.1 = p1\nfoo = bar\n",
            # индекс вне диапазона
            "[users]\nuser.255 = a\npassword.255 = p1\n",
            "[users]\nuser.0 = a\npassword.0 = p1\n",
        ]
        for body in cases:
            with self.subTest(body=body):
                with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
                    f.write("[server]\n" + body)
                    path = f.name
                with self.assertRaises(ValueError):
                    load_config(path)

    def test_users_duplicate_option_fails(self):
        import tempfile
        from awg_panel.config import load_config
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[users]\nuser.1 = a\npassword.1 = p1\nuser.1 = b\npassword.1 = p2\n")
            path = f.name
        with self.assertRaises(ValueError):
            load_config(path)

    def test_users_limit_254(self):
        import tempfile
        from awg_panel.config import MAX_USERS, load_config
        self.assertEqual(MAX_USERS, 254)
        lines = "".join(f"user.{i} = u{i}\npassword.{i} = p{i}\n" for i in range(1, 255))
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\n[users]\n" + lines)
            path = f.name
        self.assertEqual(len(load_config(path).users), 254)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\n[users]\n" + lines + "user.255 = extra\npassword.255 = x\n")
            path2 = f.name
        with self.assertRaises(ValueError):
            load_config(path2)

    def test_update_user_password(self):
        import os, tempfile
        from awg_panel.config import update_user_password, load_config
        content = (
            "[server]\nhost = 0.0.0.0\n\n"
            "[users]\nuser.1 = admin\npassword.1 = oldpass\n"
            "user.2 = guest\npassword.2 = guestpass\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".ini", delete=False,
                                         encoding="utf-8") as f:
            f.write(content)
            path = f.name
        try:
            update_user_password(path, "admin", "newpass123")
            cfg = load_config(path)
            self.assertEqual(cfg.users["admin"], "newpass123")
            self.assertEqual(cfg.users["guest"], "guestpass")
        finally:
            os.unlink(path)

    def test_update_user_password_not_found(self):
        import os, tempfile
        from awg_panel.config import update_user_password
        content = "[users]\nuser.1 = admin\npassword.1 = oldpass\n"
        with tempfile.NamedTemporaryFile("w", suffix=".ini", delete=False,
                                         encoding="utf-8") as f:
            f.write(content)
            path = f.name
        try:
            with self.assertRaises(ValueError):
                update_user_password(path, "nobody", "pw")
        finally:
            os.unlink(path)

    def test_auth_limits(self):
        import tempfile
        from awg_panel.config import load_config
        users = "[users]\nuser.1 = admin\npassword.1 = admin\n"
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nauth_max_attempts = 3\nauth_lock_minutes = 10\n" + users)
            path = f.name
        cfg = load_config(path)
        self.assertEqual(cfg.auth_max_attempts, 3)
        self.assertEqual(cfg.auth_lock_minutes, 10)
        # defaults + clamp
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nport = 8443\n" + users)
            path2 = f.name
        cfg2 = load_config(path2)
        self.assertEqual(cfg2.auth_max_attempts, 5)
        self.assertEqual(cfg2.auth_lock_minutes, 5)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nauth_max_attempts = 0\nauth_lock_minutes = 99999\n" + users)
            path3 = f.name
        cfg3 = load_config(path3)
        self.assertEqual(cfg3.auth_max_attempts, 1)
        self.assertEqual(cfg3.auth_lock_minutes, 1440)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nauth_max_attempts = garbage\nauth_lock_minutes = garbage\n" + users)
            path4 = f.name
        cfg4 = load_config(path4)
        self.assertEqual(cfg4.auth_max_attempts, 5)
        self.assertEqual(cfg4.auth_lock_minutes, 5)


class TestClientNames(unittest.TestCase):
    def _load(self, body: str):
        import tempfile
        from awg_panel.config import load_config
        users = "[users]\nuser.1 = admin\npassword.1 = admin\n"
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write(body + users)
            path = f.name
        return load_config(path)

    def test_defaults_without_section(self):
        cfg = self._load("[server]\nport = 8443\n")
        self.assertEqual(cfg.client_name_prefix, "user_")
        self.assertEqual(cfg.client_name_rand_bytes, 8)

    def test_custom(self):
        cfg = self._load("[server]\n[client_names]\nprefix = vpn-\nrand_bytes = 9\n")
        self.assertEqual(cfg.client_name_prefix, "vpn-")
        self.assertEqual(cfg.client_name_rand_bytes, 9)

    def test_garbage_and_clamp(self):
        cfg = self._load("[server]\n[client_names]\nprefix = \nrand_bytes = garbage\n")
        self.assertEqual(cfg.client_name_prefix, "user_")
        self.assertEqual(cfg.client_name_rand_bytes, 8)
        self.assertEqual(self._load("[server]\n[client_names]\nrand_bytes = 0\n").client_name_rand_bytes, 1)
        # 999 -> clamp 32, затем урезка под длину имени (<= 63):
        # префикс user_ (5) -> (63-5)//2 = 29, префикс из 1 символа -> 31.
        self.assertEqual(self._load("[server]\n[client_names]\nrand_bytes = 999\n").client_name_rand_bytes, 29)
        cfg5 = self._load("[server]\n[client_names]\nprefix = a\nrand_bytes = 999\n")
        self.assertEqual(cfg5.client_name_rand_bytes, 31)

    def test_bad_prefix_falls_back(self):
        for bad in ("bad name!", "../x", "a" * 62):
            with self.subTest(bad=bad):
                cfg = self._load(f"[server]\n[client_names]\nprefix = {bad}\n")
                self.assertEqual(cfg.client_name_prefix, "user_")

    def test_long_prefix_shrinks_rand_bytes(self):
        # префикс 32 символа -> не больше (63-32)//2 = 15 байт, иначе имя
        # не пройдёт valid_client_name() (<= 63).
        cfg = self._load("[server]\n[client_names]\nprefix = " + "p" * 32 + "\nrand_bytes = 32\n")
        self.assertEqual(cfg.client_name_prefix, "p" * 32)
        self.assertEqual(cfg.client_name_rand_bytes, 15)
        self.assertLessEqual(len(cfg.client_name_prefix) + 2 * cfg.client_name_rand_bytes, 63)
        self.assertTrue(valid_client_name(cfg.client_name_prefix + "f" * (2 * cfg.client_name_rand_bytes)))

    def test_example_has_client_names(self):
        example = (Path(__file__).resolve().parents[1] / "packaging" / "config.ini.example").read_text()
        self.assertIn("[client_names]", example)
        self.assertIn("prefix = user_", example)
        self.assertIn("rand_bytes = 8", example)


class TestManage(unittest.TestCase):
    def test_mutation_errors_and_timeouts(self):
        import subprocess
        from unittest.mock import patch
        from awg_panel import manage
        for command, args in ((manage.cmd_add, (["alice"], "--expires=7d")),
                              (manage.cmd_remove, (["alice"],)),
                              (manage.cmd_regen, (["alice"],))):
            for error, rc in ((subprocess.TimeoutExpired("manage", 120), 124),
                              (OSError("cannot execute"), 127)):
                with self.subTest(command=command.__name__, error=type(error).__name__):
                    with patch.object(manage.subprocess, "run", side_effect=error) as run:
                        result = command("/manage.sh", *args)
                    self.assertFalse(result.ok)
                    self.assertEqual(result.rc, rc)
                    self.assertEqual(run.call_args.kwargs["timeout"], 120)
            with patch.object(manage.subprocess, "run", return_value=
                              subprocess.CompletedProcess([], 1, '{"ok":false}', "failed")):
                self.assertFalse(command("/manage.sh", *args).ok)

    def test_invalid_expires_rejected_before_execution(self):
        from unittest.mock import patch
        from awg_panel import manage
        with patch.object(manage.subprocess, "run") as run:
            for flag in ("--expires=7d\n", "--expires=0d", "--expires=3651d", "--expires=7h"):
                with self.subTest(flag=flag), self.assertRaises(ValueError):
                    manage.cmd_add("/manage.sh", ["alice"], flag)
            run.assert_not_called()

    def test_parse_ok_flag(self):
        from awg_panel.manage import _parse_json_output
        r = _parse_json_output('{"ok": true, "x": 1}', 0, "")
        self.assertTrue(r.ok)
        self.assertEqual(r.data["x"], 1)
        r2 = _parse_json_output('{"ok": false}', 0, "e")
        self.assertFalse(r2.ok)
        r3 = _parse_json_output("not json", 0, "e")
        self.assertFalse(r3.ok)

    def test_add_argv_order(self):
        # Regression: --expires must sit between --yes and add.
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

    def test_run_helper_allowlist(self):
        # Helper allowlist is enforced in code (manage._HELPER_CMDS):
        # unknown commands and stray args are rejected before exec.
        from awg_panel import manage
        with self.assertRaises(ValueError):
            manage.run_helper("/usr/sbin/awg-panel-helper", "reboot")
        with self.assertRaises(ValueError):
            manage.run_helper("/usr/sbin/awg-panel-helper", "server-pubkeys", "extra")
        with self.assertRaises(ValueError):
            manage.run_helper("/usr/sbin/awg-panel-helper", "client-conf", "bad;name")

    def test_root_runs_direct_without_sudo(self):
        # Service runs as root -> manage/helper called directly.
        # Sudo path is only a fallback for non-root dev runs.
        from unittest import mock
        from awg_panel import manage
        with mock.patch.object(manage, "_is_root", lambda: True):
            self.assertEqual(
                manage._base("/root/awg/manage_amneziawg.sh"),
                ["/bin/bash", "/root/awg/manage_amneziawg.sh"],
            )
            rc_holder = {}

            import subprocess

            def fake_run(cmd, **kw):
                rc_holder["cmd"] = cmd
                return subprocess.CompletedProcess(cmd, 0, b"", b"")

            with mock.patch.object(manage.subprocess, "run", fake_run):
                manage.run_helper("/usr/sbin/awg-panel-helper", "server-pubkeys")
            self.assertEqual(
                rc_holder["cmd"][:2],
                ["/usr/sbin/awg-panel-helper", "server-pubkeys"],
            )
            self.assertNotIn("/usr/bin/sudo", rc_holder["cmd"])


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
        # Regression: 0.1.1 built as uid 1001 shipped files owned by 1001.
        build = (Path(__file__).resolve().parents[1] / "build_deb.sh").read_text()
        self.assertIn("root-owner-group", build)
        self.assertIn("chown -R 0:0", build)

    def test_postinst_no_sudoers(self):
        postinst = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "postinst").read_text()
        self.assertNotIn("sudoers", postinst)
        self.assertNotIn("visudo", postinst)
        postrm = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "postrm").read_text()
        self.assertNotIn("sudoers", postrm)
        conffiles = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "conffiles").read_text()
        self.assertNotIn("sudoers", conffiles)
        self.assertFalse(
            (Path(__file__).resolve().parents[1] / "packaging" / "sudoers").exists()
        )

    def test_postinst_tls_key_root_only(self):
        # Service runs as root -> key 600 root:root.
        postinst = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "postinst").read_text()
        self.assertIn("chmod 600 /etc/awg-panel/key.pem", postinst)
        self.assertIn("chown root:root /etc/awg-panel/key.pem", postinst)
        self.assertNotIn("chown root:awgpanel /etc/awg-panel/key.pem", postinst)

    def test_postinst_prints_next_steps(self):
        postinst = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "postinst").read_text()
        for marker in (
            "/etc/awg-panel/config.ini",
            "systemctl restart awg-panel",
            "awg-panel-set-password",
            "https://<IP",
            "[users]",
            "user.N/password.N",
        ):
            self.assertIn(marker, postinst)
        self.assertNotIn("webusername", postinst)
        self.assertNotIn("webpassword", postinst)
        # legacy password-file flow is gone (cleanup removed in stable)
        self.assertNotIn("/root/.awg-panel-initial-password", postinst)
        self.assertNotIn("awg-panel-set-password-internal", postinst)

    def test_postinst_no_web_credentials_migration(self):
        postinst = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "postinst").read_text()
        self.assertNotIn("webusername", postinst)
        self.assertNotIn("webpassword", postinst)
        self.assertIn("chmod 600 /etc/awg-panel/config.ini", postinst)

    def test_postrm_purge_full_cleanup(self):
        # 0.1.11: purge must remove what dpkg leaves behind — postinst-made
        # cert/key (not conffiles) and logs. /root/awg must never be touched.
        postrm = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "postrm").read_text()
        self.assertIn("purge)", postrm)
        for marker in (
            "rm -f /etc/awg-panel/cert.pem",
            "/etc/awg-panel/key.pem",
            "/etc/awg-panel/config.ini",
            "rm -rf /var/log/awg-panel",
        ):
            self.assertIn(marker, postrm)
        # Only real commands count — the comment names the protected paths.
        code = "\n".join(l for l in postrm.splitlines() if l.strip() and not l.strip().startswith("#"))
        self.assertNotIn("/root/awg", code)
        self.assertNotIn("/etc/amnezia", code)

    def test_service_runs_as_root_without_sudo_breaking_sandbox(self):
        # Regression: User=awgpanel + sandbox broke sudo, service runs as root.
        svc = (Path(__file__).resolve().parents[1] / "packaging" / "awg-panel.service").read_text()
        # Only real directives count — comments describe the old breakage.
        directives = [l for l in svc.splitlines() if l.strip() and not l.strip().startswith("#")]
        body = "\n".join(directives)
        self.assertIn("User=root", body)
        self.assertIn("Group=root", body)
        self.assertNotIn("CapabilityBoundingSet", body)
        self.assertNotIn("AmbientCapabilities", body)
        self.assertNotIn("NoNewPrivileges", body)
        self.assertNotIn("ReadOnlyPaths", body)
        self.assertNotIn("ProtectSystem=strict", body)
        self.assertNotIn("ProtectHome=read-only", body)

    def test_config_example_has_users_only(self):
        example = (Path(__file__).resolve().parents[1] / "packaging" / "config.ini.example").read_text()
        self.assertNotIn("webusername", example)
        self.assertNotIn("webpassword", example)
        self.assertNotIn("password_file", example)
        self.assertIn("[users]", example)
        self.assertIn("user.1 = admin", example)
        self.assertIn("password.1 = admin", example)
        self.assertIn("auth_max_attempts = 5", example)
        self.assertIn("auth_lock_minutes = 5", example)
        self.assertIn("http_redirect_port = 80", example)

    def test_control_no_sudo_dep(self):
        control = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "control").read_text()
        depends = next(l for l in control.splitlines() if l.startswith("Depends:"))
        self.assertNotIn("sudo", depends.split(":", 1)[1].split(","))

    def test_build_does_not_ship_internal_setter(self):
        build = (Path(__file__).resolve().parents[1] / "build_deb.sh").read_text()
        self.assertNotIn("awg-panel-set-password-internal", build)
        self.assertFalse(
            (Path(__file__).resolve().parents[1] / "bin" / "awg-panel-set-password-internal").exists()
        )


class TestClientPage(unittest.TestCase):
    def _render_client(self):
        from types import SimpleNamespace
        from unittest import mock
        from awg_panel import server as srv
        from awg_panel.config import PanelConfig
        from awg_panel.manage import ManageResult
        h = srv.Handler.__new__(srv.Handler)
        h.cfg = PanelConfig()
        long_line = "Endpoint = 1.2.3.4:51820 # " + "A" * 500
        conf = ("[Interface]\nPrivateKey = " + "B" * 60 + "\n"
                f"{long_line}\n[Peer]\nPublicKey = " + "C" * 60 + "\n")
        uri = "vpn://awg@" + "D" * 500
        with mock.patch.object(srv.Handler, "_sess",
                               lambda self: SimpleNamespace(csrf="t")), \
             mock.patch.object(srv, "cmd_list", lambda ms: ManageResult(
                 True, 0, [{"name": "alice", "ip": "10.0.0.2",
                            "status": "active", "expires_at": None}], "")), \
             mock.patch.object(srv, "cmd_stats", lambda ms: ManageResult(
                 True, 0, [{"name": "alice", "rx": 1, "tx": 2,
                            "last_handshake": 0}], "")), \
             mock.patch.object(srv, "run_helper") as rh:
            def side_effect(helper, *args, **kw):
                if args[:1] == ("client-conf",):
                    return 0, conf.encode(), ""
                if args[:1] == ("client-uri",):
                    return 0, (uri + "\n").encode(), ""
                return 1, b"", "no"
            rh.side_effect = side_effect
            return h._page_client("alice")

    def test_blocks_stacked_peer_conf_vpn_qr(self):
        body = self._render_client()
        self.assertIn("class=stack", body)
        self.assertNotIn("class=grid", body)
        i_peer = body.index("<h2>Пир</h2>")
        i_conf = body.index("<h2>Конфиг</h2>")
        i_vpn = body.index("<h2>vpn://</h2>")
        i_qr = body.index("<h2>QR</h2>")
        self.assertLess(i_peer, i_conf)
        self.assertLess(i_conf, i_vpn)
        self.assertLess(i_vpn, i_qr)

    def test_peer_buttons_and_qr_new_window(self):
        body = self._render_client()
        peer = body[body.index("<h2>Пир</h2>"):body.index("<h2>Конфиг</h2>")]
        self.assertIn(">Пересоздать<", peer)
        self.assertIn("Скачать .conf", peer)
        self.assertIn("QR.png", peer)
        self.assertIn("target=_blank", peer)
        self.assertIn("/client-qr?name=alice", peer)
        # each block is its own card
        self.assertEqual(body.count("<div class=card>"), 4)

    def test_peer_actions_single_row(self):
        body = self._render_client()
        peer = body[body.index("<h2>Пир</h2>"):body.index("<h2>Конфиг</h2>")]
        self.assertIn("<div class=actions>", peer)
        act = peer[peer.index("<div class=actions>"):]
        self.assertLess(act.index(">Пересоздать<"), act.index("Скачать .conf"))
        self.assertLess(act.index("Скачать .conf"), act.index("QR.png"))
        from awg_panel.server import STYLE_CSS
        self.assertIn(".actions{display:flex", STYLE_CSS)
        self.assertIn("margin-top:12px", STYLE_CSS)
        self.assertIn(".actions form{margin:0}", STYLE_CSS)

    def test_copy_buttons_conf_and_vpn(self):
        from awg_panel.server import COPY_JS
        body = self._render_client()
        i_conf_pre = body.index('id=conf-pre')
        i_vpn_pre = body.index('id=vpn-pre')
        self.assertLess(body.index("<h2>Конфиг</h2>"), i_conf_pre)
        self.assertLess(i_conf_pre, body.index("data-src=conf-pre"))
        self.assertLess(body.index("<h2>vpn://</h2>"), i_vpn_pre)
        self.assertLess(i_vpn_pre, body.index("data-src=vpn-pre"))
        self.assertEqual(body.count(">Скопировать<"), 2)
        # 0.1.9: CSP (script-src 'self') forbids inline scripts, so the page
        # only references the external file; the logic itself is asserted
        # against COPY_JS below and served by test_copy_js_static_route.
        self.assertIn('<script src="/static/copy.js" defer></script>', body)
        self.assertIn('/static/copy.js', body)
        self.assertNotIn("navigator.clipboard.writeText", body)
        self.assertIn("navigator.clipboard.writeText", COPY_JS)
        self.assertIn("execCommand('copy')", COPY_JS)
        self.assertIn("createElement('textarea')", COPY_JS)
        self.assertIn("Не скопировалось", COPY_JS)
        self.assertIn("DOMContentLoaded", COPY_JS)
        # 0.1.14: состояние «Скопировано» видно и цветом (класс copied),
        # disabled-кнопки — серым текстом вместо чёрного.
        self.assertIn("classList.add('copied')", COPY_JS)
        self.assertIn("classList.remove('copied')", COPY_JS)
        from awg_panel.server import STYLE_CSS as _CSS
        self.assertIn("button.copied{", _CSS)
        self.assertIn("button:disabled{", _CSS)

    def test_copy_js_static_route(self):
        # /static/copy.js must be served (200 + javascript) without auth,
        # otherwise CSP script-src 'self' leaves the buttons dead.
        from io import BytesIO
        from awg_panel import server as srv
        h = srv.Handler.__new__(srv.Handler)
        h.command = "GET"
        h.path = "/static/copy.js"
        h.wfile = BytesIO()
        sent = {}

        def send_response(code, msg=None):
            sent["code"] = code

        def send_header(k, v):
            sent.setdefault("hdrs", []).append((k, v))

        h.send_response = send_response
        h.send_header = send_header
        h.end_headers = lambda: sent.setdefault("ended", True)
        h.do_GET()
        self.assertEqual(sent.get("code"), 200)
        hdrs = dict(sent.get("hdrs", []))
        self.assertIn("javascript", hdrs.get("Content-Type", ""))
        csp = hdrs.get("Content-Security-Policy", "")
        self.assertIn("script-src 'self'", csp)
        raw = h.wfile.getvalue()
        self.assertIn(b"awgCopy", raw)
        self.assertEqual(raw.decode("utf-8"), srv.COPY_JS)

    def test_buttons_unified_font(self):
        from awg_panel.server import STYLE_CSS
        rule = STYLE_CSS.split("button,.btn{", 1)[1].split("}", 1)[0]
        # <button> uses the UA default font, <a class=btn> inherits the page
        # font — without font:inherit they render at different sizes.
        self.assertIn("font:inherit", rule)
        self.assertIn("padding:8px 14px", rule)

    def test_no_page_level_hscroll_css(self):
        from awg_panel.server import STYLE_CSS
        self.assertIn("body{", STYLE_CSS)
        self.assertIn("overflow-x:hidden", STYLE_CSS)
        self.assertNotIn(".grid", STYLE_CSS)
        self.assertNotIn(".tabs", STYLE_CSS)
        self.assertIn("min-width:0", STYLE_CSS)
        # overflowing element itself scrolls internally
        self.assertIn("pre{", STYLE_CSS)
        pre_rule = STYLE_CSS.split("pre{", 1)[1].split("}", 1)[0]
        self.assertIn("overflow:auto", pre_rule)
        self.assertIn("max-width:100%", pre_rule)


class TestClientsListPage(unittest.TestCase):
    def _render(self, prefix="user_", rand_bytes=8):
        from types import SimpleNamespace
        from unittest import mock
        from awg_panel import server as srv
        from awg_panel.config import PanelConfig
        from awg_panel.manage import ManageResult
        h = srv.Handler.__new__(srv.Handler)
        cfg = PanelConfig()
        cfg.client_name_prefix = prefix
        cfg.client_name_rand_bytes = rand_bytes
        h.cfg = cfg
        clients = [{"name": "alice", "ip": "10.0.0.2", "status": "active",
                    "status_code": "active", "expires_at": None}]
        with mock.patch.object(srv.Handler, "_sess",
                               lambda self: SimpleNamespace(csrf="t")), \
             mock.patch.object(srv, "cmd_list", lambda ms: ManageResult(True, 0, clients, "")), \
             mock.patch.object(srv, "cmd_stats", lambda ms: ManageResult(True, 0, [], "")), \
             mock.patch.object(srv, "run_helper", lambda helper, *a, **k: (0, b"", "")):
            return h._page_clients()

    def test_delete_disabled_until_checked(self):
        body = self._render()
        # кнопка удаления неактивна без выбора и сабмитит форму с чекбоксами
        self.assertIn('id=delbtn disabled', body)
        self.assertIn('form=delf', body)
        # JS включает/выключает её по чекбоксам (внешний файл, не инлайн)
        self.assertNotIn("getRandomValues", body)
        self.assertNotIn("<script>", body)
        from awg_panel.server import CLIENTS_JS
        self.assertIn('<script src="/static/clients.js" defer></script>', body)
        self.assertIn("getElementById('delbtn')", CLIENTS_JS)
        self.assertIn("b.disabled=!any", CLIENTS_JS)
        self.assertIn("DOMContentLoaded", CLIENTS_JS)

    def test_add_and_delete_single_row(self):
        body = self._render()
        i_add = body.index(">Добавить<")
        i_del = body.index(">Удалить выбранные<")
        self.assertLess(i_add, i_del)
        # обе кнопки лежат в одном <div class=row>, форма #delf (таблица)
        # идёт уже после него
        row_start = body.rindex("<div class=row>", 0, i_add)
        row_end = body.index("</div>", i_add)
        self.assertLess(i_del, row_end)
        self.assertIn("form=addf", body[row_start:row_end])
        self.assertIn("form=delf", body[row_start:row_end])
        self.assertIn("id=delf", body[row_end:])

    def test_generate_button_and_data_attrs(self):
        body = self._render(prefix="vpn-", rand_bytes=9)
        self.assertIn(">Сгенерировать имя<", body)
        self.assertIn("data-prefix='vpn-'", body)
        self.assertIn("data-rand-bytes='9'", body)
        self.assertIn("id=names", body)
        from awg_panel.server import CLIENTS_JS
        self.assertIn("getRandomValues", CLIENTS_JS)
        self.assertIn("Math.random", CLIENTS_JS)
        self.assertIn("data-prefix", CLIENTS_JS)

    def test_generate_appends_with_space(self):
        # повторный клик дописывает имя через пробел, а не затирает поле
        from awg_panel.server import CLIENTS_JS
        gen = CLIENTS_JS[CLIENTS_JS.index("function awgClientsGen"):]
        self.assertIn("cur.replace(", gen)
        self.assertIn("+' '+gen", gen)
        self.assertIn("cur.trim()", gen)

    def test_disabled_and_copied_styles(self):
        from awg_panel.server import STYLE_CSS
        dis = STYLE_CSS.split("button:disabled{", 1)[1].split("}", 1)[0]
        self.assertIn("color:#9ca3af", dis)
        self.assertIn("cursor:not-allowed", dis)
        cop = STYLE_CSS.split("button.copied{", 1)[1].split("}", 1)[0]
        self.assertIn("color:#9ca3af", cop)

    def test_clients_js_static_route(self):
        # /static/clients.js должен отдаваться (200 + javascript) без авторизации,
        # иначе CSP script-src 'self' оставит кнопки мёртвыми.
        from io import BytesIO
        from awg_panel import server as srv
        h = srv.Handler.__new__(srv.Handler)
        h.command = "GET"
        h.path = "/static/clients.js"
        h.wfile = BytesIO()
        sent = {}

        def send_response(code, msg=None):
            sent["code"] = code

        def send_header(k, v):
            sent.setdefault("hdrs", []).append((k, v))

        h.send_response = send_response
        h.send_header = send_header
        h.end_headers = lambda: sent.setdefault("ended", True)
        h.do_GET()
        self.assertEqual(sent.get("code"), 200)
        hdrs = dict(sent.get("hdrs", []))
        self.assertIn("javascript", hdrs.get("Content-Type", ""))
        csp = hdrs.get("Content-Security-Policy", "")
        self.assertIn("script-src 'self'", csp)
        raw = h.wfile.getvalue()
        self.assertIn(b"awgClients", raw)
        self.assertEqual(raw.decode("utf-8"), srv.CLIENTS_JS)


class TestClientsDeleteConfirm(unittest.TestCase):
    def _post(self, path, form, cmd_remove=None):
        from types import SimpleNamespace
        from awg_panel import server as srv
        from awg_panel.config import PanelConfig
        h = srv.Handler.__new__(srv.Handler)
        h.cfg = PanelConfig()
        h.path = path
        h.command = "POST"
        h.client_address = ("127.0.0.1", 12345)
        authed = SimpleNamespace(csrf="t", sid="s")
        h._authed = authed
        h._sess = lambda: authed
        h._require_auth = lambda: authed
        h._parse_form = lambda: form
        h._check_csrf = lambda f: True
        captured = {}
        h._send_auth = lambda code, body, *a, **k: captured.setdefault("send", (code, body))
        h._redirect = lambda where, cookie=None: captured.setdefault("redirect", where)
        if cmd_remove is not None:
            import unittest.mock as mock
            with mock.patch.object(srv, "cmd_remove", cmd_remove):
                h.do_POST()
        else:
            h.do_POST()
        return captured

    def test_delete_confirm_page(self):
        from types import SimpleNamespace
        from awg_panel import server as srv
        from awg_panel.config import PanelConfig
        h = srv.Handler.__new__(srv.Handler)
        h.cfg = PanelConfig()
        h._sess = lambda: SimpleNamespace(csrf="t")
        body = h._page_clients_delete_confirm(["alice", "bob"])
        self.assertIn("Удаление пользователей: Вы уверены?", body)
        self.assertIn("alice", body)
        self.assertIn("bob", body)
        self.assertIn("/clients/delete/confirm", body)
        self.assertIn("Подтвердить", body)
        self.assertIn("Отмена", body)

    def test_delete_first_post_does_not_remove(self):
        from awg_panel.manage import ManageResult
        calls = []
        cap = self._post("/clients/delete", {"sel": ["alice"], "csrf": "t"},
                         cmd_remove=lambda ms, names: calls.append(names) or ManageResult(True, 0, None, ""))
        self.assertEqual(calls, [])
        code, body = cap["send"]
        self.assertEqual(code, 200)
        self.assertIn("Удаление пользователей: Вы уверены?", body)

    def test_delete_confirm_post_removes(self):
        calls = []
        from awg_panel.manage import ManageResult
        cap = self._post("/clients/delete/confirm", {"sel": ["alice"], "csrf": "t"},
                         cmd_remove=lambda ms, names: calls.append(names) or ManageResult(True, 0, None, ""))
        self.assertEqual(calls, [["alice"]])
        self.assertEqual(cap.get("redirect"), "/clients")


class TestLoginPage(unittest.TestCase):
    def _page(self, err=""):
        from awg_panel import server as srv
        h = srv.Handler.__new__(srv.Handler)
        return h._page_login(err)

    def test_no_nav_on_login(self):
        body = self._page()
        # На входе только форма; бренд, версия и сайдбар отсутствуют.
        self.assertNotIn("<aside", body)
        self.assertNotIn("AWG Panel", body)
        self.assertNotIn("<nav", body)
        self.assertNotIn(">Система<", body)
        self.assertNotIn(">Клиенты<", body)
        self.assertNotIn(">Справка<", body)
        self.assertNotIn(">Выход<", body)
        self.assertNotIn("/logout", body)
        self.assertNotIn("/clients", body)
        self.assertNotIn("/system", body)
        self.assertNotIn("/help", body)

    def test_login_error_shown_without_nav(self):
        body = self._page("Неверный логин или пароль")
        self.assertIn("Неверный логин или пароль", body)
        self.assertNotIn("<nav", body)

    def test_autofocus_on_username(self):
        body = self._page()
        self.assertIn("name=user autocomplete=username autofocus required", body)
        self.assertEqual(body.count("autofocus"), 1)

    def test_nav_present_elsewhere(self):
        from awg_panel import server as srv
        h = srv.Handler.__new__(srv.Handler)
        full = h._layout("T", "system", "b", "csrf")
        self.assertIn(">Система<", full)
        self.assertIn(">Клиенты<", full)
        self.assertIn(">Справка<", full)
        self.assertIn('href="/help"', full)

    def test_logout_pinned_to_bottom(self):
        from awg_panel import server as srv
        h = srv.Handler.__new__(srv.Handler)
        body = h._layout("T", "system", "b", "csrf")
        # «Выход» идёт последним в nav, CSS прижимает его к низу сайдбара
        self.assertLess(body.index("/clients"), body.index("navlogout"))
        self.assertIn("nav{display:flex", srv.STYLE_CSS)
        self.assertIn("flex-direction:column", srv.STYLE_CSS)
        logout_rule = srv.STYLE_CSS.split("nav form.navlogout{", 1)[1].split("}", 1)[0]
        self.assertIn("margin:auto 0 0", logout_rule)
        # сайдбар привязан к вьюпорту: низ меню = низ видимой части,
        # скроллить страницу ради «Выхода» не нужно
        aside_rule = srv.STYLE_CSS.split("aside{", 1)[1].split("}", 1)[0]
        self.assertIn("position:sticky", aside_rule)
        self.assertIn("top:0", aside_rule)
        self.assertIn("height:100vh", aside_rule)

    def test_version_without_github_link(self):
        from awg_panel import __version__
        from awg_panel import server as srv
        # ссылка на github убрана: версия осталась, констант больше нет
        self.assertFalse(hasattr(srv, "GITHUB_URL"))
        self.assertFalse(hasattr(srv, "INSTALLER_URL"))
        h = srv.Handler.__new__(srv.Handler)
        full = h._layout("T", "system", "b", "csrf")
        self.assertIn(f"v{__version__}", full)
        self.assertNotIn("github.com", full)


class TestHttpRedirect(unittest.TestCase):
    def test_build_url(self):
        from awg_panel.server import build_https_redirect_url
        self.assertEqual(
            build_https_redirect_url("10.129.110.110:80", "/", 8443),
            "https://10.129.110.110:8443/")
        self.assertEqual(
            build_https_redirect_url("10.129.110.110", "/system", 8443),
            "https://10.129.110.110:8443/system")
        # 443 не пишется в URL
        self.assertEqual(
            build_https_redirect_url("example.com:80", "/clients", 443),
            "https://example.com/clients")
        self.assertEqual(
            build_https_redirect_url("[::1]:80", "/", 8443),
            "https://[::1]:8443/")
        # CRLF в Host -> отказ (защита от response-splitting/open-redirect)
        self.assertIsNone(build_https_redirect_url("evil.com\r\nX: y", "/", 8443))
        self.assertIsNone(build_https_redirect_url("a/b", "/", 8443))
        self.assertIsNone(build_https_redirect_url(None, "/", 8443))
        self.assertIsNone(build_https_redirect_url("", "/", 8443))
        # CRLF в path -> сброс на /
        self.assertEqual(
            build_https_redirect_url("example.com", "/a\r\nb", 8443),
            "https://example.com:8443/")

    def test_config_redirect_port(self):
        import tempfile
        from awg_panel.config import load_config
        users = "[users]\nuser.1 = admin\npassword.1 = admin\n"
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nport = 8443\n" + users)
            p = f.name
        self.assertEqual(load_config(p).http_redirect_port, 80)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nport = 8443\nhttp_redirect_port = 0\n" + users)
            p2 = f.name
        self.assertEqual(load_config(p2).http_redirect_port, 0)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nport = 8443\nhttp_redirect_port = garbage\n" + users)
            p3 = f.name
        self.assertEqual(load_config(p3).http_redirect_port, 80)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nport = 8443\nhttp_redirect_port = 99999\n" + users)
            p4 = f.name
        self.assertEqual(load_config(p4).http_redirect_port, 80)

    def test_live_redirect_only_301_no_cookies(self):
        import http.client
        import socket
        import time
        from awg_panel.config import PanelConfig
        from awg_panel.server import start_http_redirector

        def free():
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            p = s.getsockname()[1]
            s.close()
            return p

        rport, hport = free(), free()
        cfg = PanelConfig(host="127.0.0.1", port=hport, http_redirect_port=rport)
        srv = start_http_redirector(cfg)
        self.assertIsNotNone(srv)
        try:
            time.sleep(0.3)
            c = http.client.HTTPConnection("127.0.0.1", rport, timeout=5)
            c.request("GET", "/system", headers={"Host": "127.0.0.1"})
            r = c.getresponse()
            r.read()
            self.assertEqual(r.status, 301)
            self.assertEqual(r.getheader("Location"),
                             f"https://127.0.0.1:{hport}/system")
            self.assertIsNone(r.getheader("Set-Cookie"))
            # POST тоже только редирект (тело в cleartext отбрасывается)
            c2 = http.client.HTTPConnection("127.0.0.1", rport, timeout=5)
            c2.request("POST", "/login", body="user=admin",
                       headers={"Host": "127.0.0.1"})
            r2 = c2.getresponse()
            r2.read()
            self.assertEqual(r2.status, 301)
            # кривой Host -> 400, а не редирект наружу
            c3 = http.client.HTTPConnection("127.0.0.1", rport, timeout=5)
            c3.request("GET", "/", headers={"Host": "bad/host"})
            r3 = c3.getresponse()
            r3.read()
            self.assertEqual(r3.status, 400)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_same_port_disables_redirector(self):
        from awg_panel.config import PanelConfig
        from awg_panel.server import start_http_redirector
        cfg = PanelConfig(host="127.0.0.1", port=8443, http_redirect_port=8443)
        self.assertIsNone(start_http_redirector(cfg))
        cfg2 = PanelConfig(host="127.0.0.1", port=8443, http_redirect_port=0)
        self.assertIsNone(start_http_redirector(cfg2))


class TestClientsSorting(unittest.TestCase):
    def test_sort_name(self):
        from awg_panel.server import sort_clients
        clients = [{"name": "bob"}, {"name": "Alice"}, {"name": "carol"}]
        got = [c["name"] for c in sort_clients(clients, {}, "name", "asc")]
        self.assertEqual(got, ["Alice", "bob", "carol"])
        got_d = [c["name"] for c in sort_clients(clients, {}, "name", "desc")]
        self.assertEqual(got_d, ["carol", "bob", "Alice"])

    def test_sort_ip_numeric(self):
        from awg_panel.server import sort_clients
        clients = [{"name": "a", "ip": "10.0.0.10"},
                   {"name": "b", "ip": "10.0.0.2"},
                   {"name": "c", "ip": "?"}]
        got = [c["name"] for c in sort_clients(clients, {}, "ip", "asc")]
        self.assertEqual(got, ["b", "a", "c"])
        got_d = [c["name"] for c in sort_clients(clients, {}, "ip", "desc")]
        self.assertEqual(got_d, ["c", "a", "b"])

    def test_sort_status_rank(self):
        from awg_panel.server import sort_clients
        clients = [{"name": "x", "status": "s", "status_code": "no_data"},
                   {"name": "a", "status": "s", "status_code": "active"},
                   {"name": "m", "status": "s", "status_code": "recent"}]
        got = [c["name"] for c in sort_clients(clients, {}, "status", "asc")]
        self.assertEqual(got, ["a", "m", "x"])

    def test_sort_traffic_sum(self):
        from awg_panel.server import sort_clients
        clients = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        stats = {"a": {"rx": 10, "tx": 5}, "b": {"rx": 100, "tx": 0}}
        got = [c["name"] for c in sort_clients(clients, stats, "traffic", "asc")]
        self.assertEqual(got, ["c", "a", "b"])
        got_d = [c["name"] for c in sort_clients(clients, stats, "traffic", "desc")]
        self.assertEqual(got_d, ["b", "a", "c"])

    def test_sort_expires_inf_last(self):
        from awg_panel.server import sort_clients
        clients = [{"name": "inf", "expires_at": None},
                   {"name": "old", "expires_at": 100},
                   {"name": "new", "expires_at": 200}]
        got = [c["name"] for c in sort_clients(clients, {}, "expires", "asc")]
        self.assertEqual(got, ["old", "new", "inf"])

    def test_sort_invalid_fallback(self):
        from awg_panel.server import sort_clients
        clients = [{"name": "b"}, {"name": "a"}]
        got = [c["name"] for c in sort_clients(clients, {}, "bad", "bad")]
        self.assertEqual(got, ["a", "b"])

    def test_table_headers_are_sort_links(self):
        from types import SimpleNamespace
        from unittest import mock
        from awg_panel import server as srv
        from awg_panel.config import PanelConfig
        from awg_panel.manage import ManageResult
        h = srv.Handler.__new__(srv.Handler)
        h.cfg = PanelConfig()
        clients = [{"name": "alice", "ip": "10.0.0.2", "status": "active",
                    "status_code": "active", "expires_at": None}]
        with mock.patch.object(srv.Handler, "_sess",
                               lambda self: SimpleNamespace(csrf="t")), \
             mock.patch.object(srv, "cmd_list", lambda ms: ManageResult(True, 0, clients, "")), \
             mock.patch.object(srv, "cmd_stats", lambda ms: ManageResult(True, 0, [], "")), \
             mock.patch.object(srv, "run_helper", lambda helper, *a, **k: (0, b"", "")):
            body = h._page_clients("", "ip", "asc")
        for field in ("sort=name", "sort=ip", "sort=status", "sort=traffic", "sort=expires"):
            self.assertIn(field, body)
        # active sort shows arrow and flips dir
        self.assertIn("sort=ip&dir=desc", body)
        self.assertIn("STYLE_CSS" if False else "th a{", srv.STYLE_CSS)

    def test_table_rows_follow_sort(self):
        from awg_panel.server import sort_clients
        # end-to-end via _clients_table order: bob (.2) before alice (.10) on ip asc
        from types import SimpleNamespace
        from unittest import mock
        from awg_panel import server as srv
        from awg_panel.config import PanelConfig
        from awg_panel.manage import ManageResult
        h = srv.Handler.__new__(srv.Handler)
        h.cfg = PanelConfig()
        clients = [{"name": "alice", "ip": "10.0.0.10", "status": "active",
                    "status_code": "active", "expires_at": None},
                   {"name": "bob", "ip": "10.0.0.2", "status": "active",
                    "status_code": "active", "expires_at": None}]
        with mock.patch.object(srv.Handler, "_sess",
                               lambda self: SimpleNamespace(csrf="t")), \
             mock.patch.object(srv, "cmd_list", lambda ms: ManageResult(True, 0, clients, "")), \
             mock.patch.object(srv, "cmd_stats", lambda ms: ManageResult(True, 0, [], "")), \
             mock.patch.object(srv, "run_helper", lambda helper, *a, **k: (0, b"", "")):
            body_ip = h._page_clients("", "ip", "asc")
        self.assertLess(body_ip.index("bob"), body_ip.index("alice"))
        _ = sort_clients  # keep import used


class TestSystemPage(unittest.TestCase):
    def _handler(self):
        from types import SimpleNamespace
        from awg_panel import server as srv
        from awg_panel.config import PanelConfig
        h = srv.Handler.__new__(srv.Handler)
        h.cfg = PanelConfig()
        h._sess = lambda: SimpleNamespace(csrf="t")
        return h, srv

    def test_blocks_order_no_tabs(self):
        from unittest import mock
        h, srv = self._handler()
        with mock.patch.object(srv.Handler, "_awg_block",
                               lambda self: "<div class=card><h2>AWG</h2></div>"), \
             mock.patch.object(srv.Handler, "_system_block",
                               lambda self: "<div class=card><h2>Система</h2></div>"), \
             mock.patch.object(srv.Handler, "_interfaces_block",
                               lambda self: "<div class=card><h2>Интерфейсы</h2></div>"), \
             mock.patch.object(srv.Handler, "_journal_block",
                               lambda self: "<div class=card><h2>Журнал входов</h2></div>"):
            body = h._page_system()
        self.assertNotIn("class=tabs", body)
        self.assertNotIn("tab=awg", body)
        i_sys = body.index("<h2>Система</h2>")
        i_if = body.index("<h2>Интерфейсы</h2>")
        i_awg = body.index("<h2>AWG</h2>")
        i_act = body.index("Перезагрузить сервер")
        i_jour = body.index("Журнал входов")
        self.assertLess(i_sys, i_if)
        self.assertLess(i_if, i_awg)
        self.assertLess(i_awg, i_act)
        self.assertLess(i_act, i_jour)
        self.assertIn("Перезапустить awg", body)
        self.assertIn("/system/reboot", body)
        self.assertIn("/system/awg-restart", body)

    def test_confirm_texts(self):
        h, _ = self._handler()
        reboot = h._page_system_confirm("reboot")
        self.assertIn("Перезагрузка сервера: Вы уверены?", reboot)
        self.assertIn("/system/reboot", reboot)
        awg = h._page_system_confirm("awg-restart")
        self.assertIn("Перезапуск AWG: Вы уверены?", awg)
        self.assertIn("/system/awg-restart", awg)

    def test_awg_restart_calls_systemctl(self):
        import subprocess
        from unittest import mock
        from awg_panel import manage
        seen = {}

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with mock.patch.object(manage, "_is_root", lambda: True), \
             mock.patch.object(manage.subprocess, "run", fake_run):
            r = manage.cmd_awg_restart()
        self.assertTrue(r.ok)
        self.assertIn("systemctl", seen["cmd"][0])
        self.assertIn("awg-quick@awg0", seen["cmd"])

    def test_reboot_uses_systemctl_not_helper(self):
        from unittest import mock
        from awg_panel import manage
        from awg_panel import server as srv
        # reboot must not appear in helper allowlist (stays rejected)
        with self.assertRaises(ValueError):
            manage.run_helper("/usr/sbin/awg-panel-helper", "reboot")
        h, _ = self._handler()
        actions = h._actions_block()
        self.assertIn("systemctl restart awg-quick@awg0", actions)


class TestHelpPage(unittest.TestCase):
    def test_help_contains_faq_and_no_commercial_support(self):
        from types import SimpleNamespace
        from awg_panel.server import Handler
        from awg_panel.config import PanelConfig
        h = Handler.__new__(Handler)
        h.cfg = PanelConfig()
        h._sess = lambda: SimpleNamespace(csrf="t")
        body = h._page_help()
        self.assertIn('<h1>Справка</h1>', body)
        self.assertIn('href="/help" class="on"', body)
        self.assertIn("href='/instructions'", body)
        self.assertIn('github.com/thrsnknwldgthtsntpwr/awg-control-pan', body)
        self.assertNotIn('/support', body)
        self.assertNotIn('t.me/', body)
        self.assertNotIn('коммерческ', body)
        for question in ("Как добавить пользователя?", "Как удалить пользователя?",
                         "Как посмотреть QR-код?", "Как сменить пароль учётной записи?",
                         "Как перезагрузить сервер?", "Как перезапустить AWG?",
                         "Как пересоздать ключи клиента?"):
            self.assertIn(f'<summary>{question}</summary>', body)
        self.assertEqual(body.count('<details class=faq'), 10)
        self.assertEqual(body.count('</details>'), 10)


class TestPasswordPage(unittest.TestCase):
    def _handler(self):
        from types import SimpleNamespace
        from awg_panel import server as srv
        from awg_panel.config import PanelConfig
        h = srv.Handler.__new__(srv.Handler)
        h.cfg = PanelConfig()
        h._sess = lambda: SimpleNamespace(csrf="t", username="admin")
        return h, srv

    def test_password_page_fields(self):
        h, _ = self._handler()
        body = h._page_password()
        self.assertIn("<h1>Сменить пароль</h1>", body)
        self.assertIn("name=old_password", body)
        self.assertIn("name=new_password", body)
        self.assertIn("name=new_password2", body)
        self.assertIn(">Сменить пароль<", body)
        self.assertIn('href="/system"', body)

    def test_password_confirm_page(self):
        h, _ = self._handler()
        body = h._page_password_confirm()
        self.assertIn(">Подтвердить<", body)
        self.assertIn(">Отмена<", body)
        self.assertIn("/password/confirm", body)


class TestInstructionsPage(unittest.TestCase):
    def test_instructions_page(self):
        from types import SimpleNamespace
        from awg_panel import server as srv
        from awg_panel.config import PanelConfig
        h = srv.Handler.__new__(srv.Handler)
        h.cfg = PanelConfig()
        h._sess = lambda: SimpleNamespace(csrf="t")
        body = h._page_instructions()
        self.assertIn("<h1>Инструкции для пользователей</h1>", body)
        self.assertIn("AmneziaVPN", body)
        self.assertIn("AmneziaWG", body)
        self.assertIn("DefaultVPN", body)
        self.assertIn("Windows", body)
        self.assertIn("Android", body)
        self.assertIn("iOS", body)
        # аккордеон: details/summary
        self.assertIn("<details class=acc", body)
        self.assertIn("<summary", body)


class TestProxyConfig(unittest.TestCase):
    def test_base_url_normalization_and_rejection(self):
        from awg_panel.config import normalize_base_url
        for value, expected in (("", ""), ("/", ""), ("/awg/", "/awg"),
                                ("/tools/awg", "/tools/awg")):
            self.assertEqual(normalize_base_url(value), expected)
        for value in ("https://example.com/awg", "awg", "//host", "/a//b", "/a/../b",
                      "/a/./b", "/a%2fb", "/a?b", "/a#b", "/a;b", "/a\\b", "/a\nb"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_base_url(value)

    def test_load_proxy_settings(self):
        import tempfile
        import ipaddress
        from awg_panel.config import load_config
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            path.write_text("[server]\nbase_url=/tools/awg/\n"
                            "trusted_proxies=127.0.0.1, ::1/128\n"
                            "[users]\nuser.1=admin\npassword.1=test\n", encoding="utf-8")
            cfg = load_config(str(path))
            self.assertEqual(cfg.base_url, "/tools/awg")
            self.assertEqual(cfg.trusted_proxies, (ipaddress.ip_network("127.0.0.1/32"),
                                                  ipaddress.ip_network("::1/128")))
            path.write_text(path.read_text().replace("127.0.0.1, ::1/128", "bad-proxy"))
            with self.assertRaises(ValueError):
                load_config(str(path))

    def test_forwarded_ip_only_from_explicitly_trusted_peer(self):
        import ipaddress
        from email.message import Message
        from awg_panel.config import PanelConfig
        from awg_panel.server import Handler
        h = Handler.__new__(Handler)
        h.cfg = PanelConfig()
        h.headers = Message()
        h.headers["X-Real-IP"] = "198.51.100.7"
        h.headers["X-Forwarded-For"] = "192.0.2.99"
        h.client_address = ("127.0.0.1", 1234)
        self.assertEqual(h._client_ip(), "127.0.0.1")
        h.cfg.trusted_proxies = (ipaddress.ip_network("127.0.0.1/32"),)
        self.assertEqual(h._client_ip(), "198.51.100.7")
        h.client_address = ("192.0.2.1", 1234)
        self.assertEqual(h._client_ip(), "192.0.2.1")
        h.client_address = ("127.0.0.1", 1234)
        for value in ("not-an-ip", "198.51.100.7, 192.0.2.1", "fe80::1%eth0", ""):
            h.headers.replace_header("X-Real-IP", value)
            self.assertEqual(h._client_ip(), "127.0.0.1")
        h.headers.replace_header("X-Real-IP", "2001:db8::7")
        self.assertEqual(h._client_ip(), "2001:db8::7")
        h.headers["X-Real-IP"] = "192.0.2.1"
        self.assertEqual(h._client_ip(), "127.0.0.1")


class TestReviewRegressions(unittest.TestCase):
    def test_parallel_deadline_does_not_wait_for_hung_call(self):
        import threading
        import time
        from unittest.mock import patch
        from awg_panel.server import _parallel_calls
        release = threading.Event()
        finished = threading.Event()
        def hung():
            release.wait(timeout=2)
            finished.set()
        try:
            start = time.monotonic()
            with patch("awg_panel.server.FUT_TIMEOUT", 0.02), self.assertRaises(TimeoutError):
                _parallel_calls((hung,))
            self.assertLess(time.monotonic() - start, 0.5)
            self.assertFalse(finished.is_set())
        finally:
            release.set()
            self.assertTrue(finished.wait(timeout=2))

    def test_journal_reads_only_ten_lines_into_memory(self):
        import io
        from unittest.mock import patch
        from awg_panel.config import PanelConfig
        from awg_panel.server import Handler
        handler = Handler.__new__(Handler)
        handler.cfg = PanelConfig()
        stream = io.StringIO("".join(f"entry-{i}\n" for i in range(1000)))
        with patch("builtins.open", return_value=stream), patch.object(
                stream, "read", side_effect=AssertionError("unbounded journal read")):
            page = handler._journal_block()
        self.assertIn("entry-999", page)
        self.assertIn("entry-990", page)
        self.assertNotIn("entry-989", page)
        self.assertLess(page.index("entry-999"), page.index("entry-990"))

    def test_prefixed_http_redirect_lands_on_panel(self):
        from awg_panel.server import build_https_redirect_url
        self.assertEqual(build_https_redirect_url("example.com", "/?a=1", 8443, "/tools/awg"),
                         "https://example.com:8443/tools/awg/?a=1")
        self.assertEqual(build_https_redirect_url("example.com", "/tools/awg/login?a=1", 443, "/tools/awg"),
                         "https://example.com/tools/awg/login?a=1")

    def test_names_reject_trailing_newline(self):
        from awg_panel.manage import cmd_regen, run_helper
        self.assertFalse(valid_client_name("alice\n"))
        with self.assertRaises(ValueError):
            cmd_regen("unused", ["alice\n"])
        with self.assertRaises(ValueError):
            run_helper("unused", "client-conf", "alice\n")

    def test_descending_sort_preserves_name_order_for_ties(self):
        from awg_panel.server import sort_clients
        clients = [{"name": name, "status_code": "active", "expires_at": 100}
                   for name in ("bob", "alice")]
        for key in ("status", "expires"):
            self.assertEqual([c["name"] for c in sort_clients(clients, {}, key, "desc")],
                             ["alice", "bob"])

    def test_password_write_is_section_aware_and_atomic(self):
        import tempfile
        from unittest.mock import patch
        from awg_panel.config import load_config, update_user_password
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            original = ("[server]\nuser.1 = admin\npassword.1 = leave-me\n"
                        "[users]\n# Keep this comment\nUSER.01: admin\nPASSWORD.01: old\n"
                        "user.2=guest\npassword.2=guestpass\n")
            path.write_text(original, encoding="utf-8")
            for pw in ("\n[server]\nhost=bad", "pw\r\nuser.3=evil", "\t", " pass", "pass ", "x\x00"):
                with self.subTest(pw=repr(pw)), self.assertRaises(ValueError):
                    update_user_password(str(path), "admin", pw)
                self.assertEqual(path.read_text(), original)
            with patch("awg_panel.config.os.replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    update_user_password(str(path), "admin", "new")
            self.assertEqual(path.read_text(), original)
            self.assertEqual(list(Path(tmp).iterdir()), [path])
            update_user_password(str(path), "admin", "new % # ; пароль")
            self.assertEqual(load_config(str(path)).users["admin"], "new % # ; пароль")
            self.assertIn("password.1 = leave-me", path.read_text())
            self.assertIn("# Keep this comment", path.read_text())
            self.assertEqual(load_config(str(path)).users["guest"], "guestpass")

    def test_concurrent_password_writes_preserve_both_users(self):
        import tempfile
        from concurrent.futures import ThreadPoolExecutor
        from awg_panel.config import load_config, update_user_password
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            path.write_text("[users]\nuser.1=a\npassword.1=old-a\nuser.2=b\npassword.2=old-b\n")
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(update_user_password, str(path), name, "new-" + name)
                           for name in ("a", "b")]
                for future in futures:
                    future.result()
            self.assertEqual(load_config(str(path)).users, {"a": "new-a", "b": "new-b"})


class TestPanelHTTP(unittest.TestCase):
    """Real handler/HTTP/cookies, with only installer and host operations mocked."""

    def setUp(self):
        import tempfile
        import threading
        from contextlib import ExitStack
        from http.server import ThreadingHTTPServer
        from unittest.mock import patch
        from awg_panel import server
        from awg_panel.config import load_config
        from awg_panel.manage import ManageResult
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.config = self.tmp / "config.ini"
        self.config.write_text("[server]\nbase_url=/tools/awg\ntrusted_proxies=127.0.0.1\n"
                               "[users]\nuser.1=admin\npassword.1=old\nuser.2=guest\npassword.2=guest\n")

        class TestHandler(server.Handler):
            def log_message(self, *args):
                pass

        self.handler = TestHandler
        self.handler.cfg = load_config(str(self.config))
        self.handler.auth = AuthStore(dict(self.handler.cfg.users), str(self.tmp / "auth.log"))
        client = {"name": "alice", "ip": "10.0.0.2", "status_code": "active"}
        for name, data in (("cmd_list", [client]), ("cmd_stats", []), ("cmd_check", {})):
            self.stack.enter_context(patch.object(server, name, return_value=ManageResult(True, 0, data, "")))
        self.stack.enter_context(patch.object(server, "run_helper", return_value=(0, b"sample-client-data", "")))
        self.actions = {}
        for name in ("cmd_add", "cmd_remove", "cmd_regen", "cmd_awg_restart", "_schedule_reboot"):
            self.actions[name] = self.stack.enter_context(
                patch.object(server, name, return_value=ManageResult(True, 0, {}, "")))
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), self.handler)
        self.thread = threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = "/tools/awg"

    def stop_server(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, form=None, cookie=None, headers=None):
        import http.client
        from urllib.parse import urlencode
        conn = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
        head = dict(headers or {})
        if cookie:
            head["Cookie"] = cookie
        if form is not None:
            head["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            conn.request(method, path, urlencode(form, doseq=True) if form is not None else None, head)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def login(self):
        code, headers, _ = self.request("POST", self.base + "/login", {"user": "admin", "password": "old"})
        self.assertEqual(code, 303)
        self.assertEqual(headers["Location"], self.base + "/system")
        self.assertIn("Path=" + self.base + "/;", headers["Set-Cookie"])
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        return cookie, self.handler.auth.get(cookie.split("=", 1)[1])

    def test_login_and_logout_root_and_nested_prefix(self):
        for base in ("", "/awg", "/tools/awg"):
            self.base = self.handler.cfg.base_url = base
            status, _, body = self.request("GET", base + "/login")
            self.assertEqual(status, 200)
            self.assertNotIn(b"AWG Panel", body)
            self.assertNotIn(b"<aside", body)
            self.assertIn(b'login-page', body)
            cookie, session = self.login()
            self.assertEqual(self.request("POST", base + "/logout", {"csrf": "wrong"}, cookie)[0], 403)
            status, head, _ = self.request("POST", base + "/logout", {"csrf": session.csrf}, cookie)
            self.assertEqual(status, 303)
            self.assertEqual(head["Location"], base + "/login")
            self.assertIn("Path=" + base + "/;", head["Set-Cookie"])
            self.assertIn("Max-Age=0", head["Set-Cookie"])
            self.assertIsNone(self.handler.auth.get(session.sid))

    def test_every_page_url_and_asset_stays_under_prefix(self):
        from html.parser import HTMLParser
        urls = []
        class Links(HTMLParser):
            def handle_starttag(self, tag, attrs):
                urls.extend(value for key, value in attrs if key in ("href", "src", "action") and value)
        cookie, session = self.login()
        for path in ("/system", "/system/reboot", "/system/awg-restart", "/clients?sort=ip&dir=desc",
                     "/client?name=alice", "/help", "/instructions", "/password", "/logout"):
            with self.subTest(path=path):
                status, headers, body = self.request("GET", self.base + path, cookie=cookie)
                self.assertEqual(status, 200)
                self.assertIn("Path=" + self.base + "/;", headers["Set-Cookie"])
                Links().feed(body.decode())
        status, _, body = self.request("POST", self.base + "/clients/delete",
                                       {"sel": "alice", "csrf": session.csrf}, cookie)
        self.assertEqual(status, 200)
        Links().feed(body.decode())
        for url in urls:
            if not url.startswith("https://"):
                self.assertTrue(url.startswith(self.base + "/"), url)
        self.assertIn(self.base + "/static/clients.js", urls)
        self.assertIn(self.base + "/static/copy.js", urls)
        for path, ctype in (("/static/style.css", "text/css"), ("/static/copy.js", "application/javascript"),
                            ("/static/clients.js", "application/javascript"), ("/client-qr?name=alice", "image/png"),
                            ("/download?name=alice&type=conf", "application/octet-stream")):
            status, headers, _ = self.request("GET", self.base + path, cookie=cookie)
            self.assertEqual(status, 200)
            self.assertTrue(headers["Content-Type"].startswith(ctype))
        self.assertEqual(self.request("GET", self.base + "/faq", cookie=cookie)[1]["Location"], self.base + "/help#faq")
        self.assertEqual(self.request("GET", self.base + "/support", cookie=cookie)[0], 404)

    def test_prefix_boundary_and_query(self):
        for path in ("/login", "/tools/awg-evil/login", "/tools/awgx/login", "/tools/awg%2flogin"):
            for method in ("GET", "POST"):
                self.assertEqual(self.request(method, path)[0], 404)
        self.assertEqual(self.request("GET", self.base)[1]["Location"], self.base + "/system")
        self.assertEqual(self.request("GET", self.base + "/")[1]["Location"], self.base + "/system")
        self.assertEqual(self.request("GET", self.base + "/clients")[1]["Location"], self.base + "/login")

    def test_mutations_csrf_and_redirects(self):
        cookie, session = self.login()
        status, _, _ = self.request("POST", self.base + "/clients/add", {"names": "alice"}, cookie)
        self.assertEqual(status, 403)
        self.actions["cmd_add"].assert_not_called()
        for path, form, command, redirect in (
            ("/clients/add", {"names": "alice", "days": "7"}, "cmd_add", "/clients"),
            ("/clients/delete/confirm", {"sel": "alice"}, "cmd_remove", "/clients"),
            ("/clients/regen/confirm", {"sel": "alice"}, "cmd_regen", "/client?name=alice")):
            status, headers, _ = self.request("POST", self.base + path, dict(form, csrf=session.csrf), cookie)
            self.assertEqual(status, 303)
            self.assertEqual(headers["Location"], self.base + redirect)
            self.actions[command].assert_called_once()

    def test_regen_requires_confirmation_and_csrf(self):
        cookie, session = self.login()
        form = {"sel": "alice", "csrf": session.csrf}
        status, _, body = self.request("POST", self.base + "/clients/regen", form, cookie)
        self.assertEqual(status, 200)
        self.assertIn((self.base + "/clients/regen/confirm").encode(), body)
        self.assertIn((self.base + "/client?name=alice").encode(), body)
        self.assertIn("Старые конфиги перестанут работать".encode(), body)
        self.actions["cmd_regen"].assert_not_called()
        self.assertEqual(self.request("POST", self.base + "/clients/regen/confirm",
                                     {"sel": "alice", "csrf": "wrong"}, cookie)[0], 403)
        self.actions["cmd_regen"].assert_not_called()
        status, headers, _ = self.request("POST", self.base + "/clients/regen/confirm", form, cookie)
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], self.base + "/client?name=alice")
        self.actions["cmd_regen"].assert_called_once_with(self.handler.cfg.manage_script, ["alice"])

    def test_form_field_limit_rejects_before_mutation(self):
        from awg_panel.server import MAX_FORM_FIELDS
        cookie, session = self.login()
        status, _, _ = self.request("POST", self.base + "/clients/add",
                                    {"csrf": session.csrf, "names": ["alice"] * MAX_FORM_FIELDS}, cookie)
        self.assertEqual(status, 413)
        self.actions["cmd_add"].assert_not_called()

    def test_proxy_login_limit_and_journal_use_real_ip(self):
        self.handler.auth.max_attempts = 1
        form = {"user": "admin", "password": "wrong"}
        headers = {"X-Real-IP": "198.51.100.10"}
        self.assertEqual(self.request("POST", self.base + "/login", form, headers=headers)[0], 200)
        self.assertEqual(self.request("POST", self.base + "/login", form, headers=headers)[0], 429)
        other = {"X-Real-IP": "198.51.100.11", "X-Forwarded-For": "192.0.2.99"}
        self.assertEqual(self.request("POST", self.base + "/login", {"user": "admin", "password": "old"}, headers=other)[0], 303)
        log = (self.tmp / "auth.log").read_text()
        self.assertIn("ip=198.51.100.10", log)
        self.assertIn("ip=198.51.100.11", log)
        self.assertNotIn("192.0.2.99", log)

    def test_password_flow_revokes_other_sessions_and_persists(self):
        from awg_panel.config import load_config
        cookie, session = self.login()
        _, second = self.login()
        second.pending_pw = "stale"
        guest = self.handler.auth.create("127.0.0.1", "guest")
        form = {"old_password": "old", "new_password": "new % пароль", "new_password2": "new % пароль", "csrf": session.csrf}
        status, _, body = self.request("POST", self.base + "/password", form, cookie)
        self.assertEqual(status, 200)
        self.assertIn((self.base + "/password/confirm").encode(), body)
        self.assertTrue(self.handler.auth.verify("admin", "old"))
        self.assertEqual(self.request("POST", self.base + "/password/confirm", {"csrf": session.csrf}, cookie)[0], 200)
        self.assertEqual(load_config(str(self.config)).users["admin"], "new % пароль")
        self.assertTrue(self.handler.auth.verify("admin", "new % пароль"))
        self.assertFalse(self.handler.auth.verify("admin", "old"))
        self.assertIsNone(self.handler.auth.get(second.sid))
        self.assertIsNotNone(self.handler.auth.get(guest.sid))
        self.assertIsNotNone(self.handler.auth.get(session.sid))
        self.assertIsNone(session.pending_pw)

    def test_password_injection_and_write_failure(self):
        from unittest.mock import patch
        cookie, session = self.login()
        original = self.config.read_bytes()
        session.pending_pw = "previous"
        for password in ("pw\nuser.3=evil", " pw ", "pw\x00"):
            form = {"old_password": "old", "new_password": password, "new_password2": password, "csrf": session.csrf}
            self.assertEqual(self.request("POST", self.base + "/password", form, cookie)[0], 200)
            self.assertIsNone(session.pending_pw)
            self.assertEqual(self.config.read_bytes(), original)
        session.pending_pw = "new"
        with patch("awg_panel.server.update_user_password", side_effect=OSError("PRIVATE-MARKER")):
            _, _, body = self.request("POST", self.base + "/password/confirm", {"csrf": session.csrf}, cookie)
        self.assertNotIn(b"PRIVATE-MARKER", body)
        self.assertTrue(self.handler.auth.verify("admin", "old"))
        self.assertEqual(self.config.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
