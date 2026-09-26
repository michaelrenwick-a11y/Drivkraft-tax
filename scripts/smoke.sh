#!/usr/bin/env bash
# Smoke tests against the pinned upstream code. Run after bootstrap.sh.
# Outputs land in data/smoke/<timestamp>/; results summary is printed at the end.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
OTD="$ROOT/vendor/otd-spec"
OPENTAX="$ROOT/vendor/bin/opentax"
CASE="$ROOT/vendor/opentax/benchmark/cases/f1040/2025/93-mfj-w2-k1"
OUT="$ROOT/data/smoke/$(date +%Y%m%dT%H%M%S)"
mkdir -p "$OUT"

pass=0; fail=0; results=(); json=()
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
check() {
  local name="$1"; shift
  local t0=$SECONDS
  if "$@" >"$OUT/$name.log" 2>&1; then
    results+=("PASS  $name"); pass=$((pass + 1)); json+=("{\"name\":\"$name\",\"ok\":true,\"s\":$((SECONDS - t0))}")
  else
    results+=("FAIL  $name  (see ${OUT#$ROOT/}/$name.log)"); fail=$((fail + 1))
    json+=("{\"name\":\"$name\",\"ok\":false,\"s\":$((SECONDS - t0))}")
  fi
}

# 1. OTD round-trip proof (writes into proof/generated/ upstream; that dir is upstream-gitignored)
check otd-proof bash -c "cd '$OTD' && '$PY' -B proof/otd_round_trip_proof.py | tee /dev/stderr | grep -q 'Validation: ALL PASSED'"

# 2. Validator on the proof document
check otd-validate bash -c "cd '$OTD' && '$PY' -B skills/k1-otd/scripts/validate_otd.py --input proof/proof-emitted.otd.yaml"

# 3. Synthetic PDF → OTD demonstration (runner refuses existing dirs, so use a fresh one)
check otd-synthetic-demo bash -c "cd '$OTD' && '$PY' -B examples/k1-1065-2025-synthetic/run_demo.py \
  --out '$OUT/synthetic-demo' --created 2026-07-30T00:00:00Z"

# 4. OpenTax benchmark 93-mfj-w2-k1: build the return via the CLI, compare to correct.json
check opentax-93-mfj-w2-k1 "$PY" - "$OPENTAX" "$CASE" "$OUT/opentax" <<'PYEOF'
import json, os, subprocess, sys
binary, case, work = sys.argv[1:4]
os.makedirs(work, exist_ok=True)  # opentax keeps state in ./.state relative to cwd

def tax(*args):
    r = subprocess.run([binary, *args, "--json"], cwd=work, capture_output=True, text=True, timeout=60)
    if r.returncode:
        sys.exit(f"opentax {' '.join(args[:2])} failed: {r.stderr.strip()}")
    return json.loads(r.stdout)

inp = json.load(open(f"{case}/input.json"))
rid = tax("return", "create", "--year", str(inp["year"]))["returnId"]
for f in inp["forms"]:
    tax("form", "add", "--returnId", rid, "--node_type", f["node_type"], json.dumps(f["data"]))
got = tax("return", "get", "--returnId", rid)
json.dump(got, open(f"{work}/output.json", "w"), indent=2)

# Same pass rule as upstream benchmark/run_benchmark.ts: total tax, refund and
# amount owed from `summary` each within $5 (the engine rounds some lines to dollars).
def scalar(v):
    return (v[0] if v else 0) if isinstance(v, list) else (v or 0)
summary = got.get("summary", {})
correct = json.load(open(f"{case}/correct.json"))["correct"]
bad = []
for k in ("line24_total_tax", "line35a_refund", "line37_amount_owed"):
    have, want = scalar(summary.get(k)), correct[k]
    status = "ok" if abs(have - want) <= 5 else "MISMATCH"
    if status != "ok": bad.append(k)
    print(f"{status:8} {k}: expected {want}, engine {have}")
for k in sorted(set(summary) & set(correct) - {"line24_total_tax", "line35a_refund", "line37_amount_owed"}):
    print(f"{'info':8} {k}: expected {correct[k]}, engine {scalar(summary[k])}")
print(f"return {rid}")
sys.exit(1 if bad else 0)
PYEOF

# 5. Server tests (bridge goldens and refusals, benchmark 82, tools over MCP and HTTP, PDF intake)
check server-tests "$PY" -m pytest -q "$ROOT/server/tests"

printf '\nSmoke results (%s)\n' "${OUT#$ROOT/}"
printf '  %s\n' "${results[@]}"
printf '%d passed, %d failed\n' "$pass" "$fail"
# Read by the operator page (server/operator.py).
printf '{"started":"%s","finished":"%s","passed":%d,"failed":%d,"checks":[%s]}\n' "$STARTED" \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$pass" "$fail" "$(IFS=,; echo "${json[*]}")" > "$OUT/results.json"
exit $((fail > 0))
