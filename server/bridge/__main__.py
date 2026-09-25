"""Bridge one OTD K-1 and print the result.

    .venv/bin/python -m server.bridge path/to/k1.otd.yaml [--ledger]

Exit code: 0 bridged, 1 refused.
"""
import json
import sys

from .translator import bridge_k1

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) != 1:
    sys.exit(__doc__)
result = bridge_k1(args[0]).to_dict()
if "--ledger" not in sys.argv:
    result.pop("ledger")
print(json.dumps(result, indent=2, ensure_ascii=False))
sys.exit(0 if result["status"] == "ok" else 1)
