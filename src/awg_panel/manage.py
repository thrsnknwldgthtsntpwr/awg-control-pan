"""Thin wrapper over manage_amneziawg.sh --json (single source of VPN truth).

No local DB: every call shells out (via sudo when running as `awgpanel`).
Long ops (repair-module/restore) are intentionally NOT exposed in phase 1.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from .validate import valid_client_name


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
    # When running as awgpanel user, sudo rules (see packaging/sudoers)
    # allow exactly these binaries. As root (dev/UTC) call directly.
    if _is_root():
        return ["/bin/bash", manage_script]
    return ["/usr/bin/sudo", "-n", "/bin/bash", manage_script]


def _parse_json_output(stdout: str, rc: int, stderr: str) -> ManageResult:
    """Single JSON-parsing rule: stdout is exactly ONE json document (last line)."""
    out = (stdout or "").strip()
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


def run_manage(manage_script: str, *args: str, timeout: int = 60) -> ManageResult:
    cmd = _base(manage_script) + ["--json", "--no-color"] + list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ManageResult(False, 124, None, "timeout manage")
    except OSError as e:
        return ManageResult(False, 127, None, str(e))
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
    args = ["--yes"]
    if expires_flag:
        args.append(expires_flag)
    args.append("add")
    args.extend(names)
    # NOTE: --yes/--expires go BEFORE the subcommand (manage argparse order).
    # run_manage prepends --json/--no-color itself, so rebuild order here:
    cmd = _base(manage_script) + ["--json", "--no-color"] + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return ManageResult(False, 124, None, "timeout add")
    except OSError as e:
        return ManageResult(False, 127, None, str(e))
    return _parse(p)


def cmd_remove(manage_script: str, names: list[str]) -> ManageResult:
    for n in names:
        if not valid_client_name(n):
            raise ValueError(f"bad name: {n}")
    cmd = _base(manage_script) + ["--json", "--no-color", "--yes", "remove"] + names
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return ManageResult(False, 124, None, "timeout remove")
    except OSError as e:
        return ManageResult(False, 127, None, str(e))
    return _parse(p)


def cmd_regen(manage_script: str, names: list[str]) -> ManageResult:
    for n in names:
        if not valid_client_name(n):
            raise ValueError(f"bad name: {n}")
    return run_manage(manage_script, "--yes", "regen", *names, timeout=120)


def _parse(p: "subprocess.CompletedProcess[str]") -> ManageResult:
    return _parse_json_output(p.stdout, p.returncode, p.stderr)


def run_helper(helper: str, *args: str, timeout: int = 15) -> tuple[int, bytes, str]:
    """Call /usr/sbin/awg-panel-helper (sudo) for safe file reads. Returns (rc, stdout_bytes, stderr)."""
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
