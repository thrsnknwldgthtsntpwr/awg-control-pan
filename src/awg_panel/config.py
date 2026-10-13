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
    auth_log: str = "/var/log/awg-panel/auth.log"
    session_ttl_min: int = 30
    webusername: str = "admin"
    webpassword: str = "admin"


def load_config(path: str = "/etc/awg-panel/config.ini") -> PanelConfig:
    cfg = PanelConfig()
    p = Path(path)
    if not p.is_file():
        return cfg
    cp = configparser.ConfigParser()
    cp.read(p, encoding="utf-8")
    s = cp["server"] if "server" in cp else {}
    host = (s.get("host", cfg.host) or "").strip() or cfg.host
    cfg.host = host
    try:
        cfg.port = int(s.get("port", cfg.port))
    except ValueError:
        cfg.port = 8443
    if not 1 <= cfg.port <= 65535:
        cfg.port = 8443
    cfg.cert = (s.get("cert", cfg.cert) or cfg.cert).strip() or cfg.cert
    cfg.key = (s.get("key", cfg.key) or cfg.key).strip() or cfg.key
    cfg.manage_script = (s.get("manage_script", cfg.manage_script) or cfg.manage_script).strip() or cfg.manage_script
    cfg.awg_dir = (s.get("awg_dir", cfg.awg_dir) or cfg.awg_dir).strip() or cfg.awg_dir
    cfg.server_conf = (s.get("server_conf", cfg.server_conf) or cfg.server_conf).strip() or cfg.server_conf
    cfg.helper = (s.get("helper", cfg.helper) or cfg.helper).strip() or cfg.helper
    cfg.auth_log = (s.get("auth_log", cfg.auth_log) or cfg.auth_log).strip() or cfg.auth_log
    cfg.webusername = (s.get("webusername", cfg.webusername) or cfg.webusername).strip() or "admin"
    cfg.webpassword = (s.get("webpassword", cfg.webpassword) or cfg.webpassword).strip() or "admin"
    try:
        cfg.session_ttl_min = int(s.get("session_ttl_min", cfg.session_ttl_min))
    except ValueError:
        cfg.session_ttl_min = 30
    if cfg.session_ttl_min < 1:
        cfg.session_ttl_min = 1
    elif cfg.session_ttl_min > 1440:
        cfg.session_ttl_min = 1440
    return cfg
