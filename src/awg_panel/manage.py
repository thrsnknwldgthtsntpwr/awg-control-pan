"""Thin wrapper over manage_amneziawg.sh --json (single source of VPN truth).

No local DB: every call shells out directly. The service runs as root,
so no sudo is used in production. The sudo path below is only
a fallback for non-root dev runs.
Long ops (repair-module/restore) are intentionally NOT exposed in phase 1.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass

from .validate import valid_client_name

_EXPIRES_ARGV_RE = re.compile(r"^--expires=(\d+)d$")
_HELPER_CMDS = frozenset({"client-conf", "client-uri", "client-qr", "server-pubkeys", "init-info"})
_MAX_BATCH = 100
_MAX_STDOUT = 1 << 20  # 1 MiB: cap untrusted script output before json parse


@dataclass
class ManageResult:
    ok: bool
    rc: int
    data: object  # parsed JSON or None
    stderr: str


def _is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def _base(manage_script: str) -> list[str]:
    # Production: service runs as root -> direct call, no sudo.
    # Fallback keeps non-root dev working.
    # See packaging/awg-panel.service.
    if _is_root():
        return ["/bin/bash", manage_script]
    return ["/usr/bin/sudo", "-n", "/bin/bash", manage_script]


def _parse_json_output(stdout: str, rc: int, stderr: str) -> ManageResult:
    """Single JSON-parsing rule: stdout is exactly ONE json document (last line)."""
    out = (stdout or "")
    if len(out) > _MAX_STDOUT:
        out = out[-_MAX_STDOUT:]
    out = out.strip()
    data = None
    if out:
        try:
            data = json.loads(out.splitlines()[-1])
        except json.JSONDecodeError:
            return ManageResult(False, rc, None, (stderr or "")[-2000:] + " | bad json stdout")
    ok = rc == 0
    if isinstance(data, dict) and "ok" in data:
        ok = bool(data["ok"]) and rc == 0
    return ManageResult(ok, rc, data, (stderr or "")[-4000:])


def _check_batch(names: list[str]) -> None:
    if len(names) > _MAX_BATCH:
        raise ValueError(f"too many names (max {_MAX_BATCH})")


def _check_expires_flag(flag: str | None) -> None:
    if flag is None:
        return
    m = _EXPIRES_ARGV_RE.match(flag) if isinstance(flag, str) else None
    if not m:
        raise ValueError(f"bad expires flag: {flag!r}")
    if not 1 <= int(m.group(1)) <= 3650:
        raise ValueError(f"bad expires flag: {flag!r}")


def run_manage(manage_script: str, *args: str, timeout: int = 60) -> ManageResult:
    cmd = _base(manage_script) + ["--json", "--no-color"] + list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return ManageResult(False, 124, None, "timeout manage")
    except OSError:
        return ManageResult(False, 127, None, "cannot run manage script")
    return _parse_json_output(p.stdout, p.returncode, p.stderr)


def cmd_list(manage_script: str) -> ManageResult:
    return run_manage(manage_script, "list", timeout=30)


def cmd_stats(manage_script: str) -> ManageResult:
    return run_manage(manage_script, "stats", timeout=30)


def cmd_check(manage_script: str) -> ManageResult:
    return run_manage(manage_script, "check", timeout=30)


def cmd_add(manage_script: str, names: list[str], expires_flag: str | None) -> ManageResult:
    for n in names:
        if not valid_client_name(n):
            raise ValueError(f"bad name: {n}")
    _check_batch(names)
    _check_expires_flag(expires_flag)
    args = ["--yes"]
    if expires_flag:
        args.append(expires_flag)
    args.append("add")
    args.extend(names)
    # NOTE: --yes/--expires go BEFORE the subcommand (manage argparse order).
    # run_manage prepends --json/--no-color itself, so rebuild order here:
    cmd = _base(manage_script) + ["--json", "--no-color"] + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        return ManageResult(False, 124, None, "timeout add")
    except OSError:
        return ManageResult(False, 127, None, "cannot run manage script")
    return _parse(p)


def cmd_remove(manage_script: str, names: list[str]) -> ManageResult:
    for n in names:
        if not valid_client_name(n):
            raise ValueError(f"bad name: {n}")
    _check_batch(names)
    cmd = _base(manage_script) + ["--json", "--no-color", "--yes", "remove"] + names
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        return ManageResult(False, 124, None, "timeout remove")
    except OSError:
        return ManageResult(False, 127, None, "cannot run manage script")
    return _parse(p)


def cmd_regen(manage_script: str, names: list[str]) -> ManageResult:
    for n in names:
        if not valid_client_name(n):
            raise ValueError(f"bad name: {n}")
    _check_batch(names)
    return run_manage(manage_script, "--yes", "regen", *names, timeout=120)


def _parse(p: "subprocess.CompletedProcess[str]") -> ManageResult:
    return _parse_json_output(p.stdout, p.returncode, p.stderr)


def run_helper(helper: str, *args: str, timeout: int = 15) -> tuple[int, bytes, str]:
    """Call /usr/sbin/awg-panel-helper for safe file reads. Returns (rc, stdout_bytes, stderr).

    Production runs as root -> direct call. Sudo fallback only for
    non-root dev runs.
    """
    if not args or args[0] not in _HELPER_CMDS:
        raise ValueError(f"helper cmd not allowed: {args[:1]!r}")
    cmd_name = args[0]
    rest = args[1:]
    if cmd_name in ("client-conf", "client-uri", "client-qr"):
        if len(rest) != 1 or not valid_client_name(rest[0]):
            raise ValueError(f"bad helper name: {rest!r}")
    elif rest:
        raise ValueError(f"helper {cmd_name} takes no name argument")
    if _is_root():
        cmd = [helper] + list(args)
    else:
        cmd = ["/usr/bin/sudo", "-n", helper] + list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout or b"", (p.stderr or b"").decode("utf-8", "replace")[-2000:]
    except subprocess.TimeoutExpired:
        return 124, b"", "timeout helper"
    except OSError as e:
        return 127, b"", str(e)
