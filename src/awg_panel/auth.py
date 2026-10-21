"""Multi-user auth: credentials from config.ini [users], sessions in memory, journal to file."""
from __future__ import annotations

import hmac
import os
import secrets
import threading
import time
from dataclasses import dataclass, field


def _clean(v: str, limit: int = 128) -> str:
    return str(v or "").replace("\r", " ").replace("\n", " ")[:limit]


@dataclass
class Session:
    sid: str
    csrf: str
    created: float
    expires: float
    ip: str
    username: str = ""
    pending_pw: str | None = None


@dataclass
class AuthStore:
    """Credentials come from PanelConfig.users ([users] user.N /
    password.N, max 254).

    Passwords are stored in clear in /etc/awg-panel/config.ini (mode 600,
    root-only): this is the requested simplification — no separate
    password file, no hashing. Comparison is constant-time.
    """

    users: dict = field(default_factory=dict, repr=False)
    auth_log: str = "/var/log/awg-panel/auth.log"
    ttl_sec: int = 1800
    # App-level login rate-limit (NOT iptables/ufw/nftables): the service
    # itself answers 429 while an IP is blocked. max_attempts fails ->
    # block IP for lock_sec seconds.
    max_attempts: int = 5
    lock_sec: int = 300
    # Absolute cap: sliding expiry refreshes `expires`, but `created` +
    # max_lifetime_sec bounds a stolen sid even under constant use.
    max_lifetime_sec: int = 12 * 3600
    max_sessions: int = 1000
    sessions: dict = field(default_factory=dict, repr=False)
    fails: dict = field(default_factory=dict, repr=False)  # ip -> (count, blocked_until_ts, last_fail_ts)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def __post_init__(self) -> None:
        try:
            self.max_attempts = int(self.max_attempts)
        except (TypeError, ValueError):
            self.max_attempts = 5
        if self.max_attempts < 1:
            self.max_attempts = 1
        elif self.max_attempts > 100:
            self.max_attempts = 100
        try:
            self.lock_sec = int(self.lock_sec)
        except (TypeError, ValueError):
            self.lock_sec = 300
        if self.lock_sec < 60:
            self.lock_sec = 60
        elif self.lock_sec > 1440 * 60:
            self.lock_sec = 1440 * 60
        if not isinstance(self.users, dict) or not self.users:
            raise ValueError("AuthStore: пустой users (нужна секция [users])")

    def verify(self, username: str, password: str) -> bool:
        try:
            u = str(username or "")
            p = str(password or "")
            # Linear scan without early exit: no dict-lookup timing oracle
            # for "user exists". Fine for <=254 users.
            ok = False
            for eu, ep in self.users.items():
                u_ok = hmac.compare_digest(u.encode("utf-8"), str(eu or "").encode("utf-8"))
                p_ok = hmac.compare_digest(p.encode("utf-8"), str(ep or "").encode("utf-8"))
                ok = ok or (bool(u_ok and p_ok))
            if not self.users:
                return False
            # When the name is unknown the loop above still ran over all
            # entries, so timing is comparable; nothing extra needed.
            return bool(ok)
        except Exception:
            return False

    # -- sessions --
    def create(self, ip: str, username: str = "") -> Session:
        with self._lock:
            self._gc_locked()
            if len(self.sessions) >= self.max_sessions:
                # Evict oldest by creation time (bounded memory under
                # credentialed session-creation flood).
                oldest = sorted(self.sessions.items(),
                                key=lambda kv: kv[1].created)[:len(self.sessions) - self.max_sessions + 1]
                for k, _ in oldest:
                    self.sessions.pop(k, None)
            now = time.time()
            s = Session(secrets.token_urlsafe(32), secrets.token_urlsafe(32),
                        now, now + self.ttl_sec, _clean(ip, 64), _clean(username, 64))
            self.sessions[s.sid] = s
            return s

    def get(self, sid) -> Session | None:
        if not isinstance(sid, str) or not sid:
            return None
        with self._lock:
            self._gc_locked()
            s = self.sessions.get(sid)
            if not s:
                return None
            now = time.time()
            if now - s.created > self.max_lifetime_sec:
                # Absolute lifetime exceeded: force re-login.
                self.sessions.pop(sid, None)
                return None
            # Sliding expiry, capped by absolute lifetime.
            s.expires = min(now + self.ttl_sec, s.created + self.max_lifetime_sec)
            return s

    def destroy(self, sid: str) -> None:
        with self._lock:
            self.sessions.pop(sid, None)

    def gc(self) -> None:
        with self._lock:
            self._gc_locked()

    def _gc_locked(self) -> None:
        now = time.time()
        for k in [k for k, v in self.sessions.items()
                  if v.expires < now or (now - v.created) > self.max_lifetime_sec]:
            self.sessions.pop(k, None)

    def _gc_fails(self) -> None:
        with self._lock:
            self._gc_fails_locked()

    def _gc_fails_locked(self) -> None:
        now = time.time()
        for k, v in list(self.fails.items()):
            _c, until, last = v if len(v) == 3 else (v[0], v[1], 0.0)
            if until <= now and (now - last) > 600:
                self.fails.pop(k, None)
        if len(self.fails) > 10000:
            # Evict oldest entries instead of clear(): a flood of random
            # IPs must not unblock the real attacker.
            by_last = sorted(self.fails.items(),
                             key=lambda kv: kv[1][2] if len(kv[1]) >= 3 else 0.0)
            for k, _ in by_last[:1000]:
                self.fails.pop(k, None)

    # -- login rate limit: max_attempts fails -> block ip for lock_sec --
    def blocked(self, ip: str) -> bool:
        with self._lock:
            self._gc_fails_locked()
            c = self.fails.get(_clean(ip, 64))
            if not c:
                return False
            until = c[1] if len(c) >= 2 else 0.0
            return bool(until > time.time())

    def note_fail(self, ip: str) -> None:
        with self._lock:
            self._gc_fails_locked()
            ip = _clean(ip, 64)
            now = time.time()
            cur = self.fails.get(ip, (0, 0.0, 0.0))
            c = cur[0] if len(cur) >= 1 else 0
            until = cur[1] if len(cur) >= 2 else 0.0
            c += 1
            if c >= self.max_attempts:
                until = now + self.lock_sec
                c = 0
            self.fails[ip] = (c, until, now)

    def note_ok(self, ip: str) -> None:
        with self._lock:
            self.fails.pop(_clean(ip, 64), None)

    def journal(self, ip: str, user: str, ok: bool, reason: str = "") -> None:
        try:
            d = os.path.dirname(self.auth_log)
            if d:
                os.makedirs(d, exist_ok=True)
            ts = time.strftime("%F %T")
            line = (f"[{ts}] ip={_clean(ip, 64)} user={_clean(user, 64)} "
                    f"{'OK' if ok else 'FAIL'} {_clean(reason, 128)}\n")
            fd = os.open(self.auth_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, line.encode("utf-8", "replace"))
            finally:
                os.close(fd)
        except OSError:
            pass
