"""Read-only system status from /proc (no shell-out, no extra deps)."""
from __future__ import annotations

import os
import time


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def mem_info() -> dict:
    out = {"total_kb": 0, "avail_kb": 0, "free_kb": 0}
    for line in _read("/proc/meminfo").splitlines():
        if line.startswith("MemTotal:"):
            out["total_kb"] = int(line.split()[1])
        elif line.startswith("MemAvailable:"):
            out["avail_kb"] = int(line.split()[1])
        elif line.startswith("MemFree:"):
            out["free_kb"] = int(line.split()[1])
    total = out["total_kb"] or 1
    avail = out["avail_kb"] or out["free_kb"]
    out["used_kb"] = max(0, total - avail)
    out["used_pct"] = round(out["used_kb"] * 100.0 / total, 1)
    return out


def load_avg() -> dict:
    txt = _read("/proc/loadavg").strip().split()
    try:
        ncpu = os.cpu_count() or 1
    except Exception:
        ncpu = 1
    if len(txt) >= 3:
        return {"l1": txt[0], "l5": txt[1], "l15": txt[2], "cpus": ncpu}
    return {"l1": "?", "l5": "?", "l15": "?", "cpus": ncpu}


def uptime_str() -> str:
    try:
        secs = float(_read("/proc/uptime").split()[0])
    except Exception:
        return "?"
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d} дн. {h} ч."
    if h:
        return f"{h} ч. {m} мин."
    return f"{m} мин."


def net_dev() -> list[dict]:
    """Per-interface rx/tx bytes from /proc/net/dev (no transient rate)."""
    rows = []
    lines = _read("/proc/net/dev").splitlines()
    for line in lines[2:]:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        if name == "lo":
            continue
        f = rest.split()
        if len(f) < 16:
            continue
        try:
            rows.append({"if": name, "rx": int(f[0]), "tx": int(f[8])})
        except ValueError:
            continue
    return rows


def cpu_pct() -> float | None:
    """Blocking ~0.3s snapshot of /proc/stat (None on error)."""
    def snap():
        for line in _read("/proc/stat").splitlines():
            if line.startswith("cpu "):
                p = [int(x) for x in line.split()[1:8]]
                idle = p[3] + p[4]
                return sum(p), idle
        return None
    a = snap()
    if not a:
        return None
    time.sleep(0.3)
    b = snap()
    if not b:
        return None
    dtot = b[0] - a[0]
    didle = b[1] - a[1]
    if dtot <= 0:
        return None
    return round((dtot - didle) * 100.0 / dtot, 1)


def disk_usage(path: str = "/") -> dict:
    try:
        st = os.statvfs(path)  # noqa: linux-only; guarded below
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        pct = round(used * 100.0 / total, 1) if total else 0.0
        return {"total": total, "used": used, "pct": pct}
    except (OSError, AttributeError):
        # Windows dev-machine / restricted env: no statvfs — show zeroes.
        return {"total": 0, "used": 0, "pct": 0.0}


def fmt_bytes(n: int) -> str:
    f = float(n or 0)
    for u in ("B", "KiB", "MiB", "GiB", "TiB"):
        if f < 1024 or u == "TiB":
            return f"{f:.1f} {u}" if u != "B" else f"{int(f)} B"
        f /= 1024.0
    return f"{f:.1f} TiB"
