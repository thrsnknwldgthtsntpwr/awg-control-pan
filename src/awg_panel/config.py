"""Load and validate /etc/awg-panel/config.ini (single source of tunables)."""
from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_HOST_RE = re.compile(r"^[A-Za-z0-9.\-:]{1,253}$")
_LOGIN_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_USER_KEY_RE = re.compile(r"^user\.(\d+)$")
_PASS_KEY_RE = re.compile(r"^password\.(\d+)$")
_CLIENT_PREFIX_RE = re.compile(r"^[A-Za-z0-9_-]{1,61}$")

# Hard cap on panel users: [users] user.N/password.N, N = 1..254.
MAX_USERS = 254

# Bounds for [client_names] rand_bytes: mirrors `openssl rand -hex N`
# (N bytes -> 2*N hex chars appended to prefix).
CLIENT_NAME_RAND_BYTES_MIN = 1
CLIENT_NAME_RAND_BYTES_MAX = 32
# Hard cap from validate.valid_client_name(): prefix + suffix <= 63 chars.
CLIENT_NAME_MAX_LEN = 63


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
    # Canonical user map: username -> password (from [users] only).
    users: dict = field(default_factory=dict, repr=False)
    config_path: str = "/etc/awg-panel/config.ini"
    # Login rate-limit (app-level IP block, NOT iptables/ufw/nftables):
    # auth_max_attempts fails -> block IP for auth_lock_minutes.
    auth_max_attempts: int = 5
    auth_lock_minutes: int = 5
    # Generated client names ([client_names], optional): prefix + hex suffix
    # of 2*rand_bytes chars. Client-side JS reads these via data-attributes;
    # the analogue of `user_$(openssl rand -hex N)`.
    client_name_prefix: str = "user_"
    client_name_rand_bytes: int = 8


def _parse_users(cp: configparser.ConfigParser) -> dict:
    """Parse mandatory [users] section. Raises ValueError when missing or
    inconsistent: startup must fail closed, never fall back to defaults."""
    if "users" not in cp:
        raise ValueError("config [users]: секция отсутствует (нужны user.N/password.N)")
    raw = dict(cp["users"])
    if not raw:
        raise ValueError("config [users]: секция пуста (нужны user.N/password.N)")
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
        raise ValueError("config [users]: секция пуста (нужны user.N/password.N)")
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
        raise ValueError(f"config not found: {path} (нужна секция [users])")
    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(p, encoding="utf-8")
        s = cp["server"] if "server" in cp else {}
    except configparser.DuplicateOptionError as ex:
        # Duplicates must fail closed: silent fallback would open the panel
        # (or lock everyone out) without a trace.
        raise ValueError(f"config duplicate option: {ex}")
    except (configparser.Error, OSError, UnicodeDecodeError) as ex:
        raise ValueError(f"config unreadable: {ex}")
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
    _parse_client_names(cp, cfg)
    users = _parse_users(cp)  # raises ValueError -> fail closed at startup
    if len(users) > MAX_USERS:
        raise ValueError(f"config [users]: больше {MAX_USERS} пользователей")
    cfg.users = users
    cfg.config_path = path
    return cfg


def _parse_client_names(cp: configparser.ConfigParser, cfg: PanelConfig) -> None:
    """Parse optional [client_names] section (never fails startup).

    Unlike [users], bad values fall back to defaults: missing section keeps
    prefix='user_' + rand_bytes=8, garbage/clamped ints are repaired, a bad
    prefix falls back to 'user_'. The generated name must always satisfy
    valid_client_name() (<= 63 chars), so rand_bytes is additionally capped
    by the prefix length.
    """
    try:
        cn = cp["client_names"] if "client_names" in cp else {}
    except configparser.Error:
        return
    try:
        raw_prefix = cn.get("prefix", cfg.client_name_prefix)
    except configparser.Error:
        raw_prefix = cfg.client_name_prefix
    prefix = (raw_prefix or "").strip() or "user_"
    if not _CLIENT_PREFIX_RE.match(prefix):
        prefix = "user_"
    try:
        rand_bytes = int(cn.get("rand_bytes", cfg.client_name_rand_bytes))
    except (TypeError, ValueError, configparser.Error):
        rand_bytes = 8
    if rand_bytes < CLIENT_NAME_RAND_BYTES_MIN:
        rand_bytes = CLIENT_NAME_RAND_BYTES_MIN
    elif rand_bytes > CLIENT_NAME_RAND_BYTES_MAX:
        rand_bytes = CLIENT_NAME_RAND_BYTES_MAX
    max_bytes = (CLIENT_NAME_MAX_LEN - len(prefix)) // 2
    if max_bytes < CLIENT_NAME_RAND_BYTES_MIN:
        prefix = "user_"
        max_bytes = (CLIENT_NAME_MAX_LEN - len(prefix)) // 2
    if rand_bytes > max_bytes:
        rand_bytes = max_bytes
    cfg.client_name_prefix = prefix
    cfg.client_name_rand_bytes = rand_bytes


def update_user_password(config_path: str, username: str, new_password: str) -> None:
    """Записать новый пароль пользователя в password.N секции [users] config.ini.

    Точечно заменяет только строку password.N, не трогая остальное содержимое
    файла. После записи права на файл ставятся 0o600 (как у оригинального
    конфига). Вызывает ValueError, если пользователь не найден.
    """
    _user_re = re.compile(r"^user\.(\d+)\s*=\s*" + re.escape(username) + r"\s*$")
    _pass_re = re.compile(r"^password\.(\d+)\s*=")

    with open(config_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    target_idx: int | None = None
    for line in lines:
        m = _user_re.match(line.strip())
        if m:
            target_idx = int(m.group(1))
            break
    if target_idx is None:
        raise ValueError(f"пользователь {username!r} не найден в секции [users]")

    replaced = False
    for i, line in enumerate(lines):
        m = _pass_re.match(line.strip())
        if m and int(m.group(1)) == target_idx:
            lines[i] = f"password.{target_idx} = {new_password}\n"
            replaced = True
            break

    if not replaced:
        # password.N отсутствует — добавляем сразу после user.N
        for i, line in enumerate(lines):
            if line.strip() == f"user.{target_idx} = {username}":
                lines.insert(i + 1, f"password.{target_idx} = {new_password}\n")
                replaced = True
                break

    if not replaced:
        raise ValueError(f"не удалось найти password.{target_idx} для записи")

    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.chmod(config_path, 0o600)
