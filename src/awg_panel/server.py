"""HTTPS server (stdlib only): routing, sessions, HTML rendering."""
from __future__ import annotations

import datetime
import html
import ssl
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .auth import AuthStore
from .config import PanelConfig
from .manage import cmd_add, cmd_check, cmd_list, cmd_regen, cmd_remove, cmd_stats, run_helper
from .system_info import cpu_pct, disk_usage, fmt_bytes, load_avg, mem_info, net_dev, uptime_str
from .validate import expires_flag, parse_names, valid_client_name

HTMX = ('<script src="https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js" defer '
        'integrity="sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2" '
        'crossorigin="anonymous"></script>')
CSS = '<link rel="stylesheet" href="/static/style.css">'

# Cap form bodies to avoid OOM on huge POSTs.
MAX_FORM_BYTES = 1 << 20  # 1 MiB


def e(s) -> str:
    return html.escape(str(s), quote=True)


def fmt_exp(exp) -> str:
    if exp is None:
        return "бессрочно"
    try:
        ts = int(exp)
    except (TypeError, ValueError):
        return "?"
    dt = datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y")
    left = (ts - datetime.datetime.now().timestamp()) / 86400
    if left < 0:
        return f"{dt} (истёк)"
    return f"{dt} (осталось {int(left)} дн.)"


class Handler(BaseHTTPRequestHandler):
    server_version = f"awg-panel/{__version__}"
    cfg: PanelConfig = PanelConfig()  # set by main()
    auth: AuthStore = None  # set by main()

    # ---------- helpers ----------
    def log_message(self, *a):  # quieter: errors to stderr, successful hits silenced
        try:
            code = int(str(a[1])) if len(a) > 1 else 0
        except (TypeError, ValueError):
            code = 0
        if code >= 400 or code == 0:
            sys.stderr.write(f"awg-panel: {self.client_address[0]} {a[0] if a else ''}\n")

    def _cookie_sid(self) -> str | None:
        c = self.headers.get("Cookie", "")
        try:
            mors = cookies.SimpleCookie(c)
            return mors.get("awgpanel").value if "awgpanel" in mors else None
        except Exception:
            return None

    def _sess(self):
        sid = self._cookie_sid()
        return self.auth.get(sid) if sid else None

    def _client_ip(self) -> str:
        return (self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                or self.client_address[0])

    def _send(self, code: int, body: str | bytes, ctype="text/html; charset=utf-8", extra=None,
                no_store: bool = True):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if no_store:
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_auth(self, code: int, body: str | bytes, ctype="text/html; charset=utf-8",
                   extra=None, no_store: bool = True):
        """Same as _send but refreshes the session cookie (sliding expiry).

        AuthStore.get() extends server-side expiry on every request; without
        re-issuing Max-Age the browser would drop the cookie while the server
        still considers the session valid.
        """
        s = getattr(self, "_authed", None)
        extra = dict(extra or {})
        if s is not None:
            extra["Set-Cookie"] = self._set_session_cookie(s.sid)
        return self._send(code, body, ctype, extra, no_store)

    def _redirect(self, where: str, cookie: str | None = None):
        h = {"Location": where}
        if cookie is not None:
            h["Set-Cookie"] = cookie
        self._send(302, "", extra=h)

    def _set_session_cookie(self, sid: str | None) -> str:
        if sid:
            return f"awgpanel={sid}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age={self.cfg.session_ttl_min*60}"
        return "awgpanel=expired; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0"

    def _require_auth(self):
        s = self._sess()
        if not s:
            self._redirect("/login")
            return None
        self._authed = s
        return s

    def _parse_form(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            n = 0
        if n < 0:
            n = 0
        if n > MAX_FORM_BYTES:
            # Drain nothing; caller turns this into 413.
            raise ValueError("form too large")
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        out = {}
        for k, v in urllib.parse.parse_qsl(raw, keep_blank_values=True):
            if k in out:
                if isinstance(out[k], list):
                    out[k].append(v)
                else:
                    out[k] = [out[k], v]
            else:
                out[k] = v
        return out

    def _check_csrf(self, form) -> bool:
        s = self._sess()
        tok = form.get("csrf", "")
        if isinstance(tok, list):
            tok = tok[0] if tok else ""
        return bool(s and tok and hmac_eq(tok, s.csrf))

    # ---------- pages ----------
    def _layout(self, title: str, active: str, body: str, csrf: str = "") -> str:
        nav_links = "".join(
            f'<a href="{href}" class="{"on" if active==k else ""}">{label}</a>'
            for k, href, label in (("status", "/status", "Статус"),
                                   ("clients", "/clients", "Клиенты")))
        if active == "logout" or csrf:
            logout = (f"<form method=post action=/logout class=navlogout>"
                      f"<input type=hidden name=csrf value='{e(csrf)}'>"
                      f"<button type=submit class='navlink{' on' if active=='logout' else ''}'>Выход</button></form>")
        else:
            logout = '<a href="/logout">Выход</a>'
        nav = nav_links + logout
        return ("<!doctype html><html lang=ru><head><meta charset=utf-8>"
                "<meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<title>{e(title)} — AWG Panel</title>{CSS}{HTMX}</head>"
                f"<body><aside><div class=brand>AWG Panel<small>v{__version__}</small></div>"
                f"<nav>{nav}</nav></aside><main>{body}</main></body></html>")

    def _page_login(self, err=""):
        msg = f'<p class=err>{e(err)}</p>' if err else ""
        return self._layout("Вход", "", f"<div class=card style='max-width:420px'><h1>Вход</h1>{msg}"
                           "<form method=post action=/login>"
                           "<label>Логин<input name=user value=admin></label>"
                           "<label>Пароль<input type=password name=password autofocus></label>"
                           "<button>Войти</button></form>"
                           "<p class=muted>Логин/пароль из /etc/awg-panel/config.ini "
                           "(webusername/webpassword). После правок: "
                           "<code>sudo systemctl restart awg-panel</code>.</p></div>")

    def _page_status(self, tab: str) -> str:
        s = self._sess()
        csrf = s.csrf if s else ""
        tabs = (f"<div class=tabs><a href='/status?tab=server' class='{'on' if tab!='awg' else ''}'>Сервер</a>"
                f"<a href='/status?tab=awg' class='{'on' if tab=='awg' else ''}'>AWG</a></div>")
        if tab == "awg":
            return self._layout("Статус AWG", "status", f"<h1>Статус</h1>{tabs}{self._awg_block()}", csrf)
        return self._layout("Статус сервера", "status", f"<h1>Статус</h1>{tabs}{self._server_block()}", csrf)

    def _page_logout(self) -> str:
        s = self._sess()
        csrf = s.csrf if s else ""
        return self._layout("Выход", "logout",
            "<div class=card style='max-width:420px'><h1>Выйти?</h1>"
            f"<form method=post action=/logout><input type=hidden name=csrf value='{e(csrf)}'>"
            "<button>Выйти</button></form>"
            "<p><a href=/status>Остаться</a></p></div>", csrf)

    def _server_block(self) -> str:
        mem = mem_info()
        la = load_avg()
        cpu = cpu_pct()
        disk = disk_usage("/")
        nets = net_dev()
        net_rows = "".join(
            f"<tr><td>{e(n['if'])}</td><td>{e(fmt_bytes(n['rx']))}</td><td>{e(fmt_bytes(n['tx']))}</td></tr>"
            for n in nets) or "<tr><td colspan=3>нет данных</td></tr>"
        return (f"<div class=grid>"
                f"<div class=card><h2>Система</h2><table>"
                f"<tr><th>Uptime</th><td>{e(uptime_str())}</td></tr>"
                f"<tr><th>Load</th><td>{e(la['l1'])} / {e(la['l5'])} / {e(la['l15'])} (CPU: {e(la['cpus'])})</td></tr>"
                f"<tr><th>CPU</th><td>{'—' if cpu is None else f'{cpu} %'}</td></tr>"
                f"<tr><th>RAM</th><td>{e(fmt_bytes(mem['used_kb']*1024))} / {e(fmt_bytes(mem['total_kb']*1024))} ({mem['used_pct']} %)</td></tr>"
                f"<tr><th>Диск /</th><td>{e(fmt_bytes(disk['used']))} / {e(fmt_bytes(disk['total']))} ({disk['pct']} %)</td></tr>"
                f"</table><p class=muted>Источник: /proc (без выполнения manage).</p></div>"
                f"<div class=card><h2>Интерфейсы</h2><table><tr><th>Iface</th><th>RX</th><th>TX</th></tr>{net_rows}</table>"
                f"<p class=muted>Счётчики с загрузки (/proc/net/dev), не скорость.</p></div>"
                f"</div>{self._journal_block()}")

    def _awg_block(self) -> str:
        r = cmd_check(self.cfg.manage_script)
        rc, init_raw, _ = run_helper(self.cfg.helper, "init-info")
        proto = ver = "?"
        if rc == 0:
            for line in init_raw.decode("utf-8", "replace").splitlines():
                if line.startswith("AWG_PROTOCOL="):
                    proto = line.split("=", 1)[1]
                if line.startswith("SCRIPT_VERSION="):
                    ver = line.split("=", 1)[1]
        if not r.ok or not isinstance(r.data, dict):
            return (f"<div class=card><h2>AWG</h2><p class=err>manage check failed (rc={r.rc}). "
                    f"Установщик: v{e(ver)}, поколение: {e(proto)}.</p>"
                    f"<pre>{e((r.stderr or '')[-1500:])}</pre></div>")
        d = r.data
        svc = d.get("service", {})
        iface = d.get("interface", {})
        port = d.get("port", {})
        mod = d.get("module", {})
        fw = d.get("firewall", {})
        rows = (
            ("Юнит", f"{svc.get('unit','?')} — {'active' if svc.get('active') else 'DOWN'}"),
            ("Интерфейс", f"awg0 present={iface.get('present')} mtu={iface.get('mtu')} addrs={iface.get('addresses')}"),
            ("Порт", f"{port.get('number')}/{port.get('proto')} listening={port.get('listening')}"),
            ("Модуль", f"loaded={mod.get('loaded')} version={mod.get('version')}"),
            ("Клиентов (peers)", d.get("clients", {}).get("total", "?")),
            ("UFW", f"active={fw.get('ufw_active')} port_allowed={fw.get('port_allowed')} (панель не меняет)"),
            ("Поколение", d.get("protocol", proto)),
            ("Установщик", f"v{ver}"),
        )
        tr = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows)
        ok = "<p class=ok>OK</p>" if d.get("ok") else "<p class=err>Есть проблемы — смотрите manage check по SSH</p>"
        return f"<div class=card><h2>AWG</h2>{ok}<table>{tr}</table><p class=muted>Источник: manage check --json + маркер AWG_PROTOCOL.</p></div>"

    def _journal_block(self) -> str:
        try:
            with open(self.cfg.auth_log, encoding="utf-8", errors="replace") as f:
                lines = f.read().strip().splitlines()[-10:]
        except OSError:
            return ""
        if not lines:
            return ""
        rows = "".join(f"<tr><td>{e(l)}</td></tr>" for l in reversed(lines))
        return f"<div class=card><h2>Журнал входов (последние)</h2><table>{rows}</table></div>"

    def _clients_table(self, clients: list, stats_map: dict, pubkeys: dict) -> str:
        rows = []
        for c in clients:
            name = c.get("name", "?")
            ip = c.get("ip", "?")
            st = c.get("status", "?")
            code = c.get("status_code", "")
            cls = "ok" if code == "active" else ("warn" if code == "recent" else "muted")
            s = stats_map.get(name, {})
            traf = ""
            if s:
                traf = f"{fmt_bytes(s.get('rx',0))} / {fmt_bytes(s.get('tx',0))}"
            pk = pubkeys.get(name, "…")
            rows.append(
                f"<tr><td><input type=checkbox name=sel value='{e(name)}'></td>"
                f"<td><a href='/client?name={urllib.parse.quote(name)}'>{e(name)}</a></td>"
                f"<td>{e(ip)}</td><td class=mono>{e(pk)}</td>"
                f"<td class={cls}>{e(st)}</td><td>{e(traf)}</td>"
                f"<td>{e(fmt_exp(c.get('expires_at')))}</td></tr>")
        body = "".join(rows) or "<tr><td colspan=7>Клиентов нет</td></tr>"
        return (f"<table><tr><th></th><th>Имя</th><th>IP</th><th>Ключ</th>"
                f"<th>Статус</th><th>RX / TX</th><th>Срок</th></tr>{body}</table>")

    def _page_clients(self, msg="") -> str:
        s = self._sess()
        csrf = s.csrf if s else ""
        # list/stats/helper run in parallel: sequential timeouts summed to 75s+ before.
        with ThreadPoolExecutor(max_workers=3) as ex:
            fl = ex.submit(cmd_list, self.cfg.manage_script)
            fs = ex.submit(cmd_stats, self.cfg.manage_script)
            fh = ex.submit(run_helper, self.cfg.helper, "server-pubkeys")
            rl = fl.result()
            rs = fs.result()
            _rc, pk_raw, _e = fh.result()
        clients = rl.data if rl.ok and isinstance(rl.data, list) else []
        stats_map = {}
        if rs.ok and isinstance(rs.data, list):
            stats_map = {x.get("name"): x for x in rs.data}
        pubkeys = {}
        cur = ""
        for line in pk_raw.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if line.startswith("#_Name = "):
                cur = line.split("=", 1)[1].strip()
            elif line.startswith("PublicKey = ") and cur:
                pubkeys[cur] = line.split("=", 1)[1].strip()[:10] + "…"
                cur = ""
        m = f"<p class={'ok' if rl.ok else 'err'}>{e(msg)}</p>" if msg else ""
        if not rl.ok:
            m += f"<p class=err>list failed rc={rl.rc}</p><pre>{e((rl.stderr or '')[-1000:])}</pre>"
        tbl = self._clients_table(clients, stats_map, pubkeys)
        return self._layout("Клиенты", "clients",
            f"<h1>Клиенты <span class=muted>({len(clients)})</span></h1>{m}"
            "<div class=card><form method=post action=/clients/add class=row>"
            f"<input type=hidden name=csrf value='{e(csrf)}'>"
            "<input name=names placeholder='имена через пробел/запятую' required>"
            "<input name=days placeholder='дней (пусто=∞)' size=10 pattern='[0-9]*'>"
            "<button>Добавить</button></form>"
            f"<form method=post action=/clients/delete id=delf><input type=hidden name=csrf value='{e(csrf)}'>"
            "<div class=row><button>Удалить выбранные</button></div>"
            f"{tbl}</form>"
            "<p class=muted>Таблица = manage list --json (+stats, ключи из awg0.conf). "
            "Удаление множественное чекбоксами. Имя-ссылка → карточка.</p></div>", csrf)

    def _page_client(self, name: str) -> str:
        s0 = self._sess()
        csrf0 = s0.csrf if s0 else ""
        if not valid_client_name(name):
            return self._layout("Клиент", "clients", "<p class=err>bad name</p>", csrf0)
        with ThreadPoolExecutor(max_workers=4) as ex:
            fl = ex.submit(cmd_list, self.cfg.manage_script)
            fs = ex.submit(cmd_stats, self.cfg.manage_script)
            f1 = ex.submit(run_helper, self.cfg.helper, "client-conf", name)
            f2 = ex.submit(run_helper, self.cfg.helper, "client-uri", name)
            rl = fl.result()
            rs = fs.result()
            rc1, conf, _e1 = f1.result()
            rc2, uri, _e2 = f2.result()
        info = {}
        if rl.ok and isinstance(rl.data, list):
            info = next((c for c in rl.data if c.get("name") == name), {})
        st = next((c for c in (rs.data if rs.ok and isinstance(rs.data, list) else []) if c.get("name") == name), {})
        conf_txt = conf.decode("utf-8", "replace") if rc1 == 0 else "(нет .conf — regen?)"
        uri_txt = uri.decode("utf-8", "replace").strip() if rc2 == 0 else ""
        traf = f"{fmt_bytes(st.get('rx',0))} / {fmt_bytes(st.get('tx',0))}" if st else "—"
        hs = st.get("last_handshake", 0) if st else 0
        hs_s = datetime.datetime.fromtimestamp(hs).strftime("%d.%m.%Y %H:%M") if hs else "никогда"
        return self._layout(name, "clients",
            f"<h1><a href=/clients>Клиенты</a> / {e(name)}</h1>"
            "<div class=grid>"
            f"<div class=card><h2>Пир</h2><table>"
            f"<tr><th>IP</th><td>{e(info.get('ip','?'))} {e(info.get('client_ipv6','') or '')}</td></tr>"
            f"<tr><th>Статус</th><td>{e(info.get('status','?'))}</td></tr>"
            f"<tr><th>Срок</th><td>{e(fmt_exp(info.get('expires_at')))}</td></tr>"
            f"<tr><th>Трафик RX/TX</th><td>{e(traf)}</td></tr>"
            f"<tr><th>Handshake</th><td>{e(hs_s)}</td></tr>"
            "</table>"
            f"<form method=post action=/clients/regen class=row><input type=hidden name=csrf value='{e(csrf0)}'>"
            f"<input type=hidden name=sel value='{e(name)}'><button>Пересоздать файлы</button></form>"
            f"<p><a class=btn href='/download?name={urllib.parse.quote(name)}&type=conf'>Скачать .conf</a> "
            f"<a class=btn href='/client-qr?name={urllib.parse.quote(name)}'>QR (png)</a></p></div>"
            f"<div class=card><h2>Конфиг</h2><pre>{e(conf_txt)}</pre>"
            + (f"<h2>vpn://</h2><pre class=wrap>{e(uri_txt)}</pre>" if uri_txt else "")
            + (f"<h2>QR</h2><img src='/client-qr?name={urllib.parse.quote(name)}' alt=QR style='max-width:260px'>"
               if rc1 == 0 else "")
            + "</div></div>", csrf0)

    # ---------- HTTP verbs ----------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ("/",):
            return self._redirect("/status")
        if u.path == "/static/style.css":
            return self._send(200, STYLE_CSS, "text/css; charset=utf-8", no_store=False)
        if u.path == "/login":
            return self._send(200, self._page_login())
        if u.path == "/logout":
            # GET never destroys the session (logout-CSRF): shows confirmation,
            # real logout is POST /logout with CSRF. Unauthed users go to login.
            s = self._sess()
            if not s:
                return self._redirect("/login")
            self._authed = s
            return self._send_auth(200, self._page_logout())
        s = self._require_auth()
        if not s:
            return
        if u.path == "/status":
            tab = (q.get("tab", ["server"])[0] or "server")
            return self._send_auth(200, self._page_status(tab if tab in ("server", "awg") else "server"))
        if u.path == "/clients":
            return self._send_auth(200, self._page_clients())
        if u.path == "/client":
            return self._send_auth(200, self._page_client(q.get("name", [""])[0]))
        if u.path == "/client-qr":
            name = q.get("name", [""])[0]
            if not valid_client_name(name):
                return self._send_auth(400, "bad name", "text/plain")
            rc, data, err = run_helper(self.cfg.helper, "client-qr", name)
            if rc != 0:
                return self._send_auth(404, "not found", "text/plain")
            return self._send_auth(200, data, "image/png")
        if u.path == "/download":
            name = q.get("name", [""])[0]
            typ = q.get("type", ["conf"])[0]
            if not valid_client_name(name) or typ not in ("conf", "vpnuri"):
                return self._send_auth(400, "bad request", "text/plain")
            act = "client-conf" if typ == "conf" else "client-uri"
            rc, data, err = run_helper(self.cfg.helper, act, name)
            if rc != 0:
                return self._send_auth(404, "not found", "text/plain")
            fn = f"{name}.{'conf' if typ=='conf' else 'vpnuri.txt'}"
            return self._send_auth(200, data, "application/octet-stream",
                              {"Content-Disposition": f"attachment; filename=\"{fn}\""})
        return self._send_auth(404, "not found", "text/plain")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        ip = self._client_ip()
        if u.path == "/login":
            if self.auth.blocked(ip):
                self.auth.journal(ip, "-", False, "rate-limited")
                return self._send(429, self._page_login("Слишком много попыток, подождите 5 мин"))
            try:
                form = self._parse_form()
            except ValueError:
                return self._send(413, self._page_login("Форма слишком большая"))
            pw = form.get("password", "")
            if isinstance(pw, list):
                pw = pw[0] if pw else ""
            user = form.get("user", "")
            if isinstance(user, list):
                user = user[0] if user else ""
            user = (user or "").strip() or "admin"
            if self.auth.verify(user, pw):
                self.auth.note_ok(ip)
                self.auth.journal(ip, user, True)
                s = self.auth.create(ip)
                return self._redirect("/status", self._set_session_cookie(s.sid))
            self.auth.note_fail(ip)
            self.auth.journal(ip, user, False, "bad credentials")
            return self._send(200, self._page_login("Неверный логин или пароль"))
        s = self._require_auth()
        if not s:
            return
        try:
            form = self._parse_form()
        except ValueError:
            return self._send_auth(413, "form too large", "text/plain")
        if u.path == "/logout":
            # Real logout: CSRF-protected POST. GET only shows confirmation.
            if not self._check_csrf(form):
                return self._send_auth(403, "bad csrf", "text/plain")
            sid = self._cookie_sid()
            if sid:
                self.auth.destroy(sid)
            return self._redirect("/login", self._set_session_cookie(None))
        if not self._check_csrf(form):
            return self._send_auth(403, "bad csrf", "text/plain")

        def sel_list() -> tuple[list[str], list[str]]:
            v = form.get("sel", [])
            if isinstance(v, str):
                v = [v]
            ok = [x for x in v if valid_client_name(x)]
            bad = [x for x in v if not valid_client_name(x)]
            return ok, bad

        if u.path == "/clients/add":
            names_raw = form.get("names", "")
            if isinstance(names_raw, list):
                names_raw = names_raw[0]
            days = form.get("days", "")
            if isinstance(days, list):
                days = days[0]
            ok_names, bad = parse_names(names_raw)
            if bad:
                return self._send_auth(200, self._page_clients(f"Плохие имена: {', '.join(bad)}"))
            if not ok_names:
                return self._send_auth(200, self._page_clients("Пусто: укажите имена"))
            try:
                flag = expires_flag(days)
            except ValueError as ex:
                return self._send_auth(200, self._page_clients(str(ex)))
            r = cmd_add(self.cfg.manage_script, ok_names, flag)
            if r.ok:
                return self._redirect("/clients")
            return self._send_auth(200, self._page_clients(f"add failed rc={r.rc}: {(r.stderr or '')[-500:]}"))
        if u.path == "/clients/delete":
            names, bad = sel_list()
            if bad:
                return self._send_auth(200, self._page_clients(f"Плохие имена в выборе: {', '.join(bad)}"))
            if not names:
                return self._send_auth(200, self._page_clients("Ничего не выбрано"))
            r = cmd_remove(self.cfg.manage_script, names)
            if r.ok:
                return self._redirect("/clients")
            return self._send_auth(200, self._page_clients(f"remove failed rc={r.rc}: {(r.stderr or '')[-500:]}"))
        if u.path == "/clients/regen":
            names, bad = sel_list()
            if bad:
                return self._send_auth(200, self._page_clients(f"Плохие имена в выборе: {', '.join(bad)}"))
            if not names:
                return self._send_auth(200, self._page_clients("Ничего не выбрано для regen"))
            r = cmd_regen(self.cfg.manage_script, names)
            if r.ok:
                if len(names) == 1:
                    return self._redirect("/client?name=" + urllib.parse.quote(names[0]))
                return self._redirect("/clients")
            return self._send_auth(200, self._page_clients(f"regen failed rc={r.rc}: {(r.stderr or '')[-500:]}"))
        return self._send_auth(404, "not found", "text/plain")


def hmac_eq(a: str, b: str) -> bool:
    import hmac as _h
    return _h.compare_digest(a, b)


STYLE_CSS = """*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#eef1f5;color:#1f2937;display:flex;min-height:100vh}
aside{width:220px;background:#1f2937;color:#cbd5e1;display:flex;flex-direction:column;padding:18px 0;flex-shrink:0}
.brand{color:#fff;font-weight:700;font-size:18px;padding:0 20px 16px}.brand small{display:block;color:#94a3b8;font-weight:400;font-size:11px}
nav a{display:block;color:#cbd5e1;text-decoration:none;padding:10px 20px}nav a.on,nav a:hover{background:#374151;color:#fff}
nav form.navlogout{margin:0;padding:0}nav button.navlink{display:block;width:100%;text-align:left;background:none;border:0;color:#cbd5e1;padding:10px 20px;font:inherit;cursor:pointer;border-radius:0}nav button.navlink.on,nav button.navlink:hover{background:#374151;color:#fff}
main{flex:1;padding:24px;max-width:1200px}h1{margin:0 0 16px;font-size:22px}.card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:16px}
table{width:100%;border-collapse:collapse;background:#fff}th,td{border:1px solid #e2e8f0;padding:8px;text-align:left;font-size:13px}th{background:#f1f5f9}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.row{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
input{padding:8px;border:1px solid #cbd5e1;border-radius:6px}button,.btn{background:#e2e8f0;border:1px solid #cbd5e1;border-radius:6px;padding:8px 14px;cursor:pointer;text-decoration:none;color:#111;display:inline-block}
button:hover,.btn:hover{background:#cbd5e1}.tabs{margin-bottom:12px}.tabs a{padding:6px 14px;border:1px solid #cbd5e1;text-decoration:none;color:#111;background:#fff}.tabs a.on{background:#1f2937;color:#fff}
.err{color:#b91c1c}.ok{color:#15803d}.warn{color:#b45309}.muted{color:#64748b;font-size:12px}.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
pre{background:#0f172a;color:#e2e8f0;padding:12px;border-radius:6px;overflow:auto;font-size:12px}pre.wrap{white-space:pre-wrap;word-break:break-all}
label{display:block;margin:8px 0}input[name=user],input[name=password],input[name=names]{width:100%}
@media(max-width:800px){aside{width:150px}.grid{grid-template-columns:1fr}}
"""


def run(cfg: PanelConfig):
    import os as _os
    auth = AuthStore(cfg.webusername, cfg.webpassword, cfg.auth_log, cfg.session_ttl_min * 60)
    Handler.cfg = cfg
    Handler.auth = auth
    if not (_os.path.isfile(cfg.cert) and _os.path.isfile(cfg.key)):
        raise SystemExit(
            f"TLS cert/key not found: cert={cfg.cert} key={cfg.key} "
            "(postinst normally creates them; check /etc/awg-panel/config.ini)")
    srv = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ctx.load_cert_chain(cfg.cert, cfg.key)
    except (OSError, ssl.SSLError) as ex:
        raise SystemExit(f"TLS load failed ({cfg.cert}, {cfg.key}): {ex}")
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(f"awg-panel https://{cfg.host}:{cfg.port} (manage={cfg.manage_script})")
    srv.serve_forever()
