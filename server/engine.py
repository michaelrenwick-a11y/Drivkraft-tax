"""Thin wrapper over the pinned `opentax` CLI.

OpenTax keeps its state in ./.state/returns relative to its cwd, so every call
takes an explicit working directory (one per case, never the repo root).
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import OPENTAX_BIN

TIMEOUT_S = 60


class EngineError(Exception):
    def __init__(self, message: str, *, fix_hint: str = "", detail: Any = None):
        super().__init__(message)
        self.fix_hint = fix_hint
        self.detail = detail


def _run(args: list[str], cwd: Path) -> Any:
    if not OPENTAX_BIN.exists():
        raise EngineError("opentax binary not found", fix_hint="Run scripts/bootstrap.sh")
    cwd.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run([str(OPENTAX_BIN), *args, "--json"], cwd=cwd,
                           capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise EngineError(f"opentax {args[0]} {args[1]} timed out", fix_hint="Retry; check the input size") from exc
    if r.returncode:
        raise EngineError(f"opentax {args[0]} {args[1]} failed", detail=r.stderr.strip(),
                          fix_hint="See detail for the engine's validation message")
    return json.loads(r.stdout) if r.stdout.strip() else None


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str            # number | string | boolean | enum
    nonnegative: bool
    optional: bool
    enum: tuple[str, ...] = ()


_FIELD_LINE = re.compile(r"^ {4}(\w+)\s{2,}(\w+)(.*)$")


@lru_cache(maxsize=None)
def node_schema(node_type: str) -> dict[str, FieldSpec]:
    """Per-item field specs for an array node, read from `opentax node inspect`.

    Parsing the binary's own schema keeps the bridge's allowlist and ≥0 checks
    in lockstep with the pinned engine.
    """
    info = _run(["node", "inspect", "--node_type", node_type], Path.cwd())
    specs: dict[str, FieldSpec] = {}
    for line in info["schema"]:
        m = _FIELD_LINE.match(line)
        if not m:
            continue
        name, typ, rest = m.groups()
        enum = ()
        if typ == "enum":
            enum = tuple(v.strip() for v in rest.split("(optional)")[0].split("|"))
        specs[name] = FieldSpec(name, typ, "≥0" in rest, "(optional)" in rest, enum)
    if not specs:
        raise EngineError(f"could not read the {node_type} schema", fix_hint="Check the opentax version pin")
    return specs


class Return:
    """One OpenTax return living in `workdir`."""

    def __init__(self, workdir: Path, return_id: str):
        self.workdir = workdir
        self.id = return_id

    @classmethod
    def create(cls, workdir: Path, year: int) -> "Return":
        return cls(workdir, _run(["return", "create", "--year", str(year)], workdir)["returnId"])

    def add_form(self, node_type: str, data: dict) -> str:
        out = _run(["form", "add", "--returnId", self.id, "--node_type", node_type, json.dumps(data)], self.workdir)
        return out["id"]

    def get(self) -> dict:
        return _run(["return", "get", "--returnId", self.id], self.workdir)
