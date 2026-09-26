"""Filesystem locations shared by the server package."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
OTD_SPEC = VENDOR / "otd-spec"
OTD_SCRIPTS = OTD_SPEC / "skills" / "k1-otd" / "scripts"
OTD_TAXONOMY = OTD_SPEC / "taxonomies" / "irs-k1-1065-2025.yaml"
OPENTAX_BIN = VENDOR / "bin" / "opentax"
PYTHON = ROOT / ".venv" / "bin" / "python"
# Runtime data. Tests point DRIVKRAFT_DATA at a temp dir.
DATA = Path(os.environ.get("DRIVKRAFT_DATA") or ROOT / "data")
OTD_SYNTHETIC = OTD_SPEC / "examples" / "k1-1065-2025-synthetic"
OTD_PROOF = OTD_SPEC / "proof" / "proof-emitted.otd.yaml"
OPENTAX_BENCH = VENDOR / "opentax" / "benchmark" / "cases" / "f1040" / "2025"
FIXTURES = ROOT / "server" / "tests" / "fixtures"


def load_env() -> None:
    """Read <repo>/.env (gitignored) into os.environ without overriding real env vars:
    ANTHROPIC_API_KEY, DRIVKRAFT_CHAT_*, BIZORA_API_KEY, BIZORA_BASE_URL, DRIVKRAFT_INVITE_CODE."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            os.environ.setdefault(m[1], m[2].strip("'\""))
