"""Load and validate /etc/awg-panel/config.ini (single source of tunables)."""
from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, field
from pathlib import Path

_HOST_RE = re.compile(r"^[A-Za-z0-9.\-:]{1,253}$")
_LOGIN_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_USER_KEY_RE = re.compile(r"^user\.(\d+)$")
_PASS_KEY_RE = re.compile(r"^password\.(\d+)$")

# Hard cap on panel users (0.1.10+): [users] user.N/password.N, N = 1..254.
MAX_USERS = 254


@dataclass
class PanelConfig:
    host: str = "0.0.0.0"
    port: int = 8443
    # Plain-HTTP redirector: :http_redirect_port -> https://<host>:port/.
    # 0 = disabled (only HTTPS stays). Standard = 80.
    http_redirect_port: int = 80
    cert: str = "/etc/awg-panel/cert.pem"
    key: str = "/etc/awg-panel/key.pem"
    manage_script: str = "/root/awg/manage_amneziawg.sh"
    awg_dir: str = "/root/awg"
    server_conf: str = "/etc/amnezia/amneziawg/awg0.conf"
    helper: str = "/usr/sbin/awg-panel-helper"
    auth_log: str = "/var/log/awg-panel/auth.log"
    session_ttl_min: int = 30
    # Legacy single-user fallback (pre-0.1.10): used only when [users]
    # section is absent. When [users] is present it takes precedence.
    webusername: str = "admin"
    webpassword: str = field(default="admin", repr=False)
    # Canonical user map (0.1.10+): username -> password.
    users: dict = field(default_factory=dict, repr=False)
    # Login rate-limit (app-level IP block, NOT iptables/ufw/nftables):
    # auth_max_attempts fails -> block IP for auth_lock_minutes.
    auth_max_attempts: int = 5
    auth_lock_minutes: int = 5


def _parse_users(cp: configparser.ConfigParser) -> dict | None:
    """Parse [users] section. Returns None when section is absent/empty
    (caller falls back to legacy single user). Raises ValueError on any
    inconsistency: startup must fail closed, never silently remap pairs."""
    if "users" not in cp:
        return None
    raw = dict(cp["users"])
    if not raw:
        return None
    user_idx: dict[int, str] = {}
    pass_idx: dict[int, str] = {}
    for key, val in raw.items():
        m = _USER_KEY_RE.match(key)
        if m:
            idx = int(m.group(1))
            if not 1 <= idx <= MAX_USERS:
                raise ValueError(f"config [users]: {key} вне диапазона 1..{MAX_USERS}")
            if idx in user_idx:
                raise ValueError(f"config [users]: дубль {key}")
            user_idx[idx] = val
            continue
        m = _PASS_KEY_RE.match(key)
        if m:
            idx = int(m.group(1))
            if not 1 <= idx <= MAX_USERS:
                raise ValueError(f"config [users]: {key} вне диапазона 1..{MAX_USERS}")
            if idx in pass_idx:
                raise ValueError(f"config [users]: дубль {key}")
            pass_idx[idx] = val
            continue
        raise ValueError(f"config [users]: неизвестный ключ {key!r} (нужны user.N/password.N)")
    idxs = set(user_idx) | set(pass_idx)
    if not idxs:
        return None
    if len(idxs) > MAX_USERS:
        raise ValueError(f"config [users]: больше {MAX_USERS} пользователей")
    users: dict[str, str] = {}
    for idx in sorted(idxs):
        if idx not in user_idx:
            raise ValueError(f"config [users]: password.{idx} без user.{idx}")
        if idx not in pass_idx:
            raise ValueError(f"config [users]: user.{idx} без password.{idx}")
        name = (user_idx[idx] or "").strip()
        if not _LOGIN_RE.match(name):
            raise ValueError(f"config [users]: user.{idx}: логин 1..64 [A-Za-z0-9_.-]")
        if name in users:
            raise ValueError(f"config [users]: дубль логина {name!r}")
        pw = pass_idx[idx]
        if pw is None or not pw.strip():
            raise ValueError(f"config [users]: password.{idx}: пустой пароль запрещён")
        if "\n" in pw or "\r" in pw:
            raise ValueError(f"config [users]: password.{idx}: переводы строк запрещены")
        users[name] = pw.strip("\r\n")
    if len(users) > MAX_USERS:
        raise ValueError(f"config [users]: больше {MAX_USERS} пользователей")
    return users


def load_config(path: str = "/etc/awg-panel/config.ini") -> PanelConfig:
    cfg = PanelConfig()
    p = Path(path)
    if not p.is_file():
        cfg.users = {cfg.webusername: cfg.webpassword}
        return cfg
    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(p, encoding="utf-8")
        s = cp["server"] if "server" in cp else {}
    except configparser.DuplicateOptionError as ex:
        # Duplicates must fail closed: silent fallback to admin/admin
        # would open the panel (or lock everyone out) without a trace.
        raise ValueError(f"config duplicate option: {ex}")
    except (configparser.Error, OSError, UnicodeDecodeError):
        # Broken config (no section header, bad encoding, unreadable):
        # fail safe to defaults instead of crashing the service.
        cfg.users = {cfg.webusername: cfg.webpassword}
        return cfg
    host = (s.get("host", cfg.host) or "").strip() or cfg.host
    cfg.host = host if _HOST_RE.match(host) else "0.0.0.0"
    try:
        cfg.port = int(s.get("port", cfg.port))
    except (TypeError, ValueError):
        cfg.port = 8443
    if not 1 <= cfg.port <= 65535:
        cfg.port = 8443
    try:
        cfg.http_redirect_port = int(s.get("http_redirect_port", cfg.http_redirect_port))
    except (TypeError, ValueError):
        cfg.http_redirect_port = 80
    if cfg.http_redirect_port != 0 and not 1 <= cfg.http_redirect_port <= 65535:
        cfg.http_redirect_port = 80
    cfg.cert = (s.get("cert", cfg.cert) or cfg.cert).strip() or cfg.cert
    cfg.key = (s.get("key", cfg.key) or cfg.key).strip() or cfg.key
    cfg.manage_script = (s.get("manage_script", cfg.manage_script) or cfg.manage_script).strip() or cfg.manage_script
    cfg.awg_dir = (s.get("awg_dir", cfg.awg_dir) or cfg.awg_dir).strip() or cfg.awg_dir
    cfg.server_conf = (s.get("server_conf", cfg.server_conf) or cfg.server_conf).strip() or cfg.server_conf
    cfg.helper = (s.get("helper", cfg.helper) or cfg.helper).strip() or cfg.helper
    cfg.auth_log = (s.get("auth_log", cfg.auth_log) or cfg.auth_log).strip() or cfg.auth_log
    cfg.webusername = (s.get("webusername", cfg.webusername) or cfg.webusername).strip() or "admin"
    # Passwords are NOT stripped: spaces are significant. Only treat
    # whitespace-only as missing. ConfigParser with interpolation=None
    # allows % in passwords.
    _pw = s.get("webpassword", None)
    if _pw is None or not _pw.strip():
        cfg.webpassword = "admin"
    else:
        cfg.webpassword = _pw.strip("\r\n")
    try:
        cfg.session_ttl_min = int(s.get("session_ttl_min", cfg.session_ttl_min))
    except (TypeError, ValueError):
        cfg.session_ttl_min = 30
    if cfg.session_ttl_min < 1:
        cfg.session_ttl_min = 1
    elif cfg.session_ttl_min > 1440:
        cfg.session_ttl_min = 1440
    try:
        cfg.auth_max_attempts = int(s.get("auth_max_attempts", cfg.auth_max_attempts))
    except (TypeError, ValueError):
        cfg.auth_max_attempts = 5
    if cfg.auth_max_attempts < 1:
        cfg.auth_max_attempts = 1
    elif cfg.auth_max_attempts > 100:
        cfg.auth_max_attempts = 100
    try:
        cfg.auth_lock_minutes = int(s.get("auth_lock_minutes", cfg.auth_lock_minutes))
    except (TypeError, ValueError):
        cfg.auth_lock_minutes = 5
    if cfg.auth_lock_minutes < 1:
        cfg.auth_lock_minutes = 1
    elif cfg.auth_lock_minutes > 1440:
        cfg.auth_lock_minutes = 1440
    users = _parse_users(cp)  # raises ValueError -> fail closed at startup
    if users is None:
        users = {cfg.webusername: cfg.webpassword}
    if len(users) > MAX_USERS:
        raise ValueError(f"config [users]: больше {MAX_USERS} пользователей")
    cfg.users = users
    return cfg
