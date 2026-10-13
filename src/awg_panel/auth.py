"""Single-admin auth: credentials from config.ini, sessions in memory, journal to file."""
from __future__ import annotations

import hmac
import os
import secrets
import time
from dataclasses import dataclass, field


@dataclass
class Session:
    sid: str
    csrf: str
    created: float
    expires: float
    ip: str


@dataclass
class AuthStore:
    """Credentials come from PanelConfig (webusername/webpassword).

    Password is stored in clear in /etc/awg-panel/config.ini (mode 600,
    root-only): this is the requested simplification — no separate
    password file, no hashing. Comparison is constant-time.
    """

    username: str = "admin"
    password: str = "admin"
    auth_log: str = "/var/log/awg-panel/auth.log"
    ttl_sec: int = 1800
    sessions: dict = field(default_factory=dict)
    fails: dict = field(default_factory=dict)  # ip -> (count, blocked_until_ts, last_fail_ts)

    def verify(self, username: str, password: str) -> bool:
        try:
            u_ok = hmac.compare_digest(str(username or ""), str(self.username or ""))
            p_ok = hmac.compare_digest(str(password or ""), str(self.password or ""))
            return bool(u_ok and p_ok)
        except Exception:
            return False

    # -- sessions --
    def create(self, ip: str) -> Session:
        self.gc()
        s = Session(secrets.token_urlsafe(32), secrets.token_urlsafe(32),
                    time.time(), time.time() + self.ttl_sec, ip)
        self.sessions[s.sid] = s
        return s

    def get(self, sid: str) -> Session | None:
        self.gc()
        s = self.sessions.get(sid)
        if not s:
            return None
        # sliding expiry
        s.expires = time.time() + self.ttl_sec
        return s

    def destroy(self, sid: str) -> None:
        self.sessions.pop(sid, None)

    def gc(self) -> None:
        now = time.time()
        for k in [k for k, v in self.sessions.items() if v.expires < now]:
            self.sessions.pop(k, None)

    def _gc_fails(self) -> None:
        now = time.time()
        for k, v in list(self.fails.items()):
            _c, until, last = v if len(v) == 3 else (v[0], v[1], 0.0)
            if until <= now and (now - last) > 600:
                self.fails.pop(k, None)
        if len(self.fails) > 10000:
            self.fails.clear()

    # -- login rate limit: 5 fails -> block ip 5 min --
    def blocked(self, ip: str) -> bool:
        self._gc_fails()
        c = self.fails.get(ip)
        if not c:
            return False
        until = c[1] if len(c) >= 2 else 0.0
        return bool(until > time.time())

    def note_fail(self, ip: str) -> None:
        self._gc_fails()
        now = time.time()
        cur = self.fails.get(ip, (0, 0.0, 0.0))
        c = cur[0] if len(cur) >= 1 else 0
        until = cur[1] if len(cur) >= 2 else 0.0
        c += 1
        if c >= 5:
            until = now + 300
            c = 0
        self.fails[ip] = (c, until, now)

    def note_ok(self, ip: str) -> None:
        self.fails.pop(ip, None)

    def journal(self, ip: str, user: str, ok: bool, reason: str = "") -> None:
        try:
            os.makedirs(os.path.dirname(self.auth_log) or ".", exist_ok=True)
            ts = time.strftime("%F %T")
            with open(self.auth_log, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] ip={ip} user={user} {'OK' if ok else 'FAIL'} {reason}\n")
        except OSError:
            pass
