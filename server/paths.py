"""Filesystem locations shared by the server package."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
OTD_SPEC = VENDOR / "otd-spec"
OTD_SCRIPTS = OTD_SPEC / "skills" / "k1-otd" / "scripts"
OTD_TAXONOMY = OTD_SPEC / "taxonomies" / "irs-k1-1065-2025.yaml"
OPENTAX_BIN = VENDOR / "bin" / "opentax"
PYTHON = ROOT / ".venv" / "bin" / "python"
DATA = ROOT / "data"
