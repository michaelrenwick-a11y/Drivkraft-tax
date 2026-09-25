"""Filesystem locations shared by the server package."""
import os
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
