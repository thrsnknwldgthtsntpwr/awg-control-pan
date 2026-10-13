"""Load and validate /etc/awg-panel/config.ini (single source of tunables)."""
from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PanelConfig:
    host: str = "0.0.0.0"
    port: int = 8443
    cert: str = "/etc/awg-panel/cert.pem"
    key: str = "/etc/awg-panel/key.pem"
    manage_script: str = "/root/awg/manage_amneziawg.sh"
    awg_dir: str = "/root/awg"
    server_conf: str = "/etc/amnezia/amneziawg/awg0.conf"
    helper: str = "/usr/sbin/awg-panel-helper"
    password_file: str = "/etc/awg-panel/password"
    auth_log: str = "/var/log/awg-panel/auth.log"
    session_ttl_min: int = 30


def load_config(path: str = "/etc/awg-panel/config.ini") -> PanelConfig:
    cfg = PanelConfig()
    p = Path(path)
    if not p.is_file():
        return cfg
    cp = configparser.ConfigParser()
    cp.read(p, encoding="utf-8")
    s = cp["server"] if "server" in cp else {}
    cfg.host = s.get("host", cfg.host)
    try:
        cfg.port = int(s.get("port", cfg.port))
    except ValueError:
        cfg.port = 8443
    if not 1 <= cfg.port <= 65535:
        cfg.port = 8443
    cfg.cert = s.get("cert", cfg.cert)
    cfg.key = s.get("key", cfg.key)
    cfg.manage_script = s.get("manage_script", cfg.manage_script)
    cfg.awg_dir = s.get("awg_dir", cfg.awg_dir)
    cfg.server_conf = s.get("server_conf", cfg.server_conf)
    cfg.helper = s.get("helper", cfg.helper)
    cfg.password_file = s.get("password_file", cfg.password_file)
    cfg.auth_log = s.get("auth_log", cfg.auth_log)
    try:
        cfg.session_ttl_min = int(s.get("session_ttl_min", cfg.session_ttl_min))
    except ValueError:
        cfg.session_ttl_min = 30
    return cfg
