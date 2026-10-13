"""Validation shared by web layer and manage wrapper (mirrors manage rules)."""
from __future__ import annotations

import re

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,63}$")


def valid_client_name(name: str) -> bool:
    return bool(_NAME_RE.match(name))


def parse_names(raw: str) -> tuple[list[str], list[str]]:
    """Split textarea/comma/space separated input into (ok, bad)."""
    parts = re.split(r"[\s,;]+", (raw or "").strip())
    ok, bad = [], []
    seen = set()
    for p in parts:
        if not p:
            continue
        if valid_client_name(p) and p not in seen:
            ok.append(p)
            seen.add(p)
        elif p not in seen:
            bad.append(p)
            seen.add(p)
    return ok, bad


def expires_flag(days: str | None) -> str | None:
    """User gives only days (per spec). Empty/None -> permanent (no flag)."""
    if days is None:
        return None
    s = days.strip()
    if s == "" or s == "0":
        return None
    if not s.isdigit():
        raise ValueError("Срок задаётся только целым числом дней")
    d = int(s)
    if not 1 <= d <= 3650:
        raise ValueError("Срок: 1..3650 дней")
    return f"--expires={d}d"
