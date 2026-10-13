"""Single-admin auth: PBKDF2 password file, in-memory sessions, login journal."""
from __future__ import annotations

import hashlib
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
    password_file: str
    auth_log: str
    ttl_sec: int = 1800
    sessions: dict = field(default_factory=dict)
    fails: dict = field(default_factory=dict)  # ip -> (count, blocked_until_ts, last_fail_ts)

    # -- password file: "salt_hex:iterations:hash_hex" (pbkdf2-sha256) --
    def verify(self, password: str) -> bool:
        try:
            with open(self.password_file, encoding="utf-8") as f:
                raw = f.read().strip()
            salt_h, it_s, hash_h = raw.split(":")
            it = int(it_s)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_h), it)
            return hmac.compare_digest(dk.hex(), hash_h)
        except Exception:
            return False

    @staticmethod
    def hash_password(password: str, iterations: int = 200_000) -> str:
        salt = os.urandom(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
        return f"{salt.hex()}:{iterations}:{dk.hex()}"

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
