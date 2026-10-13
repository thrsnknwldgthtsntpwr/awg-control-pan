"""Validation shared by web layer and manage wrapper (mirrors manage rules)."""
from __future__ import annotations

import re

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
_EXPIRES_RE = re.compile(r"^[0-9]{1,4}$")

# Caps to bound CPU/ARG_MAX on batch ops (see server MAX_SEL).
MAX_PARSE_NAMES = 200
MAX_PARSE_INPUT = 64 * 1024


def valid_client_name(name) -> bool:
    return isinstance(name, str) and bool(_NAME_RE.match(name))


def parse_names(raw) -> tuple[list[str], list[str]]:
    """Split textarea/comma/space separated input into (ok, bad)."""
    if not isinstance(raw, str):
        raw = str(raw or "")
    if len(raw) > MAX_PARSE_INPUT:
        raw = raw[:MAX_PARSE_INPUT]
    parts = re.split(r"[\s,;]+", raw.strip())
    ok, bad = [], []
    seen = set()
    for p in parts:
        if not p:
            continue
        if len(ok) + len(bad) >= MAX_PARSE_NAMES:
            break
        if valid_client_name(p) and p not in seen:
            ok.append(p)
            seen.add(p)
        elif p not in seen:
            bad.append(p)
            seen.add(p)
    return ok, bad


def expires_flag(days) -> str | None:
    """User gives only days (per spec). Empty/None -> permanent (no flag)."""
    if days is None:
        return None
    if not isinstance(days, str):
        raise ValueError("Срок задаётся только целым числом дней")
    s = days.strip()
    if s == "" or s == "0":
        return None
    if not _EXPIRES_RE.match(s):
        raise ValueError("Срок задаётся только целым числом дней")
    d = int(s)
    if not 1 <= d <= 3650:
        raise ValueError("Срок: 1..3650 дней")
    return f"--expires={d}d"
