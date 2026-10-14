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

    def test_web_credentials(self):
        import tempfile
        from awg_panel.config import load_config
        # defaults when missing
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nport = 8443\n")
            path = f.name
        cfg = load_config(path)
        self.assertEqual(cfg.webusername, "admin")
        self.assertEqual(cfg.webpassword, "admin")
        self.assertEqual(cfg.users, {"admin": "admin"})
        # custom values
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nwebusername = boss\nwebpassword = s3cret\n")
            path2 = f.name
        cfg2 = load_config(path2)
        self.assertEqual(cfg2.webusername, "boss")
        self.assertEqual(cfg2.webpassword, "s3cret")
        self.assertEqual(cfg2.users, {"boss": "s3cret"})
        # empty falls back to admin
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nwebusername = \nwebpassword = \n")
            path3 = f.name
        cfg3 = load_config(path3)
        self.assertEqual(cfg3.webusername, "admin")
        self.assertEqual(cfg3.webpassword, "admin")

    def test_users_numbered(self):
        import tempfile
        from awg_panel.config import load_config
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nwebusername = boss\nwebpassword = s3cret\n"
                    "[users]\nuser.1 = user1\npassword.1 = password1\n"
                    "user.2 = user2\npassword.2 = password2\n")
            path = f.name
        cfg = load_config(path)
        # [users] wins over legacy
        self.assertEqual(cfg.users, {"user1": "password1", "user2": "password2"})

    def test_users_legacy_fallback(self):
        import tempfile
        from awg_panel.config import load_config
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nwebusername = solo\nwebpassword = s3cret\n")
            path = f.name
        self.assertEqual(load_config(path).users, {"solo": "s3cret"})

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

    def test_auth_limits(self):
        import tempfile
        from awg_panel.config import load_config
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nauth_max_attempts = 3\nauth_lock_minutes = 10\n")
            path = f.name
        cfg = load_config(path)
        self.assertEqual(cfg.auth_max_attempts, 3)
        self.assertEqual(cfg.auth_lock_minutes, 10)
        # defaults + clamp
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nport = 8443\n")
            path2 = f.name
        cfg2 = load_config(path2)
        self.assertEqual(cfg2.auth_max_attempts, 5)
        self.assertEqual(cfg2.auth_lock_minutes, 5)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nauth_max_attempts = 0\nauth_lock_minutes = 99999\n")
            path3 = f.name
        cfg3 = load_config(path3)
        self.assertEqual(cfg3.auth_max_attempts, 1)
        self.assertEqual(cfg3.auth_lock_minutes, 1440)
        with tempfile.NamedTemporaryFile("w+", suffix=".ini", delete=False) as f:
            f.write("[server]\nauth_max_attempts = garbage\nauth_lock_minutes = garbage\n")
            path4 = f.name
        cfg4 = load_config(path4)
        self.assertEqual(cfg4.auth_max_attempts, 5)
        self.assertEqual(cfg4.auth_lock_minutes, 5)


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
        # and legacy sudoers must allow that shape (see packaging/sudoers).
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

    def test_root_runs_direct_without_sudo(self):
        # 0.1.4: service runs as root -> manage/helper called directly.
        # Sudo path is only a fallback for legacy non-root installs.
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

    def test_postinst_tls_key_root_only(self):
        # 0.1.4: service runs as root -> key 600 root:root.
        # (0.1.2 was 600 root:awgpanel = restart-loop; 0.1.3 was 640
        # root:awgpanel for the awgpanel user. Both obsolete now.)
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
            "webusername",
            "webpassword",
        ):
            self.assertIn(marker, postinst)
        # legacy password-file flow is gone (only cleanup rm stays)
        self.assertNotIn("/root/.awg-panel-initial-password", postinst)
        self.assertNotIn("| /usr/sbin/awg-panel-set-password-internal", postinst)
        self.assertIn("rm -f /usr/sbin/awg-panel-set-password-internal", postinst)

    def test_postinst_migrates_web_credentials(self):
        postinst = (Path(__file__).resolve().parents[1] / "packaging" / "DEBIAN" / "postinst").read_text()
        self.assertIn("webusername = admin", postinst)
        self.assertIn("webpassword = admin", postinst)
        self.assertIn("chmod 600 /etc/awg-panel/config.ini", postinst)

    def test_service_runs_as_root_without_sudo_breaking_sandbox(self):
        # Regression 0.1.3: User=awgpanel + CapabilityBoundingSet=(empty) +
        # ProtectSystem=strict + ReadOnlyPaths broke sudo:
        # "unable to change to root gid: Operation not permitted",
        # "error initializing audit plugin sudoers_audit" ->
        # "manage check failed (rc=1)" / "list failed rc=1" in UI.
        # 0.1.4 runs as root with no such sandbox.
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

    def test_config_example_has_web_credentials(self):
        example = (Path(__file__).resolve().parents[1] / "packaging" / "config.ini.example").read_text()
        self.assertIn("webusername = admin", example)
        self.assertIn("webpassword = admin", example)
        self.assertNotIn("password_file", example)
        # 0.1.10: multi-user section + tunable rate-limit
        self.assertIn("[users]", example)
        self.assertIn("user.1 = admin", example)
        self.assertIn("password.1 = admin", example)
        self.assertIn("auth_max_attempts = 5", example)
        self.assertIn("auth_lock_minutes = 5", example)

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
        from awg_panel.server import COPY_JS, COPY_TAG
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
        self.assertIn(COPY_TAG, body)
        self.assertIn('/static/copy.js', body)
        self.assertNotIn("navigator.clipboard.writeText", body)
        self.assertIn("navigator.clipboard.writeText", COPY_JS)
        self.assertIn("execCommand('copy')", COPY_JS)
        self.assertIn("createElement('textarea')", COPY_JS)
        self.assertIn("Не скопировалось", COPY_JS)
        self.assertIn("DOMContentLoaded", COPY_JS)

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
        self.assertIn(".grid>*{min-width:0}", STYLE_CSS)
        self.assertIn("min-width:0", STYLE_CSS)
        # overflowing element itself scrolls internally
        self.assertIn("pre{", STYLE_CSS)
        pre_rule = STYLE_CSS.split("pre{", 1)[1].split("}", 1)[0]
        self.assertIn("overflow:auto", pre_rule)
        self.assertIn("max-width:100%", pre_rule)


if __name__ == "__main__":
    unittest.main()
