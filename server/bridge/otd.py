"""Load OTD documents and run the upstream validator on them.

The validator runs as-is in a subprocess (ground rule 4: call upstream, don't
fork it). A small shim imports its `validate()` and prints the result as JSON
so we get structured errors instead of scraping text.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..paths import OTD_SCRIPTS, PYTHON

TIMEOUT_S = 60

_SHIM = """
import contextlib, io, json, sys
sys.path.insert(0, sys.argv[1])
import validate_otd
with contextlib.redirect_stdout(io.StringIO()):
    try:
        result = validate_otd.validate(sys.argv[2])
    except Exception as exc:  # ValidatorConfigurationError and anything unexpected
        result = {"validator_error": f"{type(exc).__name__}: {exc}"}
print(json.dumps(result, default=str))
"""


@dataclass
class Validation:
    passes: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unverified_paths: list[str] = field(default_factory=list)
    validator_error: str | None = None


def validate(path: Path) -> Validation:
    try:
        r = subprocess.run([str(PYTHON), "-B", "-c", _SHIM, str(OTD_SCRIPTS), str(path)],
                           capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return Validation(False, validator_error="validator timed out")
    if r.returncode:
        return Validation(False, validator_error=r.stderr.strip()[-2000:] or f"exit {r.returncode}")
    out = json.loads(r.stdout)
    if "validator_error" in out:
        return Validation(False, validator_error=out["validator_error"])
    return Validation(
        passes=bool(out["passes"]),
        errors=list(out["errors"]),
        warnings=list(out["warnings"]),
        unverified_paths=list(out.get("unverified_paths") or []),
    )


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
