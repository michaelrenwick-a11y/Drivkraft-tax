# Upstream Pins

| Project | Repo | Pinned commit | License | Read on |
|---|---|---|---|---|
| OTD spec | https://github.com/opentaxdocument/otd-spec | `be6452a` (2026-09-21) | CC BY 4.0 | 2026-09-25 |
| OpenTax engine | https://github.com/filedcom/opentax | `c4c7d72` (2026-09-24) = release **v2.0.4** | AGPL v3 / commercial | 2026-09-25 |

Fetch with `scripts/bootstrap.sh` (needs git, curl, [uv](https://docs.astral.sh/uv/)). It clones both pins into `vendor/`, downloads the `opentax-<os>-<arch>` release binary for v2.0.4 into `vendor/bin/opentax`, and runs `uv sync` to create `.venv` (Python 3.11) from `pyproject.toml`/`uv.lock`. That holds the OTD pins (`ruamel.yaml`, `simplejson`, `PyYAML`, `pdfplumber`, `pypdf`) and the server's deps (`mcp` 2.x, `fastapi`, `uvicorn`, `pypdfium2`; `pytest` and `httpx` in the dev group). Keep the OTD pins in sync with `otd-spec`'s requirements files when the pin moves. Then run `scripts/smoke.sh`.

Key upstream paths:
- OTD taxonomy: `taxonomies/irs-k1-1065-2025.yaml`
- OTD validator: `skills/k1-otd/scripts/validate_otd.py`
- OTD fixtures: `proof/proof-emitted.otd.yaml`, `examples/k1-1065-2025-synthetic/`, `tests/fixtures/hostile-k1/`
- OpenTax K-1 input: `forms/f1040/nodes/inputs/k1_partnership/index.ts`
- OpenTax K-1 benchmarks: `benchmark/cases/f1040/2025/93-mfj-w2-k1/`, `95-single-w2-k1-1099r-1099int-1099div-1099b/`

## Upstream verification results

**2026-09-25, `scripts/smoke.sh`: 5/5 pass** (the fifth check, `bridge-tests`, was added in Phase 1) (macOS arm64, Python 3.11.16, opentax 2.0.4). Upstream checkouts stay clean after the run.

| Test | Result | Notes |
|---|---|---|
| OTD round-trip proof (`proof/otd_round_trip_proof.py`) | PASS | 70 indexed nodes, 5 statements; all 5 selected constraints pass |
| `validate_otd.py --input proof/proof-emitted.otd.yaml` | PASS | 0 errors, 0 warnings, 0 unverified |
| Synthetic PDF → OTD (`examples/k1-1065-2025-synthetic/run_demo.py`) | PASS | 27-page synthetic PDF; 52 face fields projected (39 present, 9 verified-absent, 4 blank, 1 missing). Bounded claim: `full_source_document_extraction: false`, `all_source_detail_records_reconciled: false` |
| OpenTax benchmark `93-mfj-w2-k1` via CLI | PASS | Total tax 10,068.18, refund 8,053 (expected 8,053.20), owed 0; same $5 rule as upstream `run_benchmark.ts` |

Things learned that matter for later phases:
- **OpenTax stores state in `./.state/returns` relative to the cwd.** The server must run it from a per-case working dir (e.g. `data/cases/<id>/calc/`), never the repo root.
- **CLI flow:** `return create --year` → `form add --node_type <type> '<json>'` per form → `return get --json` returns `summary` (7 headline lines) plus `lines` (per-line values, often `[value, value]` arrays) and `forms` (active nodes). Also `return validate` (MeF rules) and `return export --type mef|pdf` for Phase 8.
- **The `93-mfj-w2-k1` benchmark K-1 carries no amounts**, only `partnership_name`/`partnership_ein`. It proves the node plumbing, not K-1 math. **Resolved in Phase 1:** benchmark `82-single-w2-k1-1099r-1099int-1099div` has one K-1 with real amounts (Boxes 1, 2, 5, 6a, 6b, 9a). Its OTD twin `server/tests/fixtures/bench-82-oak-ventures.otd.yaml` bridges to the identical item and reproduces the benchmark within $5 (`test_bench_82_fixture_reproduces_the_benchmark`). That test is the Phase 3 check. Of the 17 K-1 benchmarks, the others use at most Boxes 1, 2, 5, 6a, 6b, 9a, 13 and 14a; several carry many K-1s (56 and 73 have 28 each).
- **K-1 engine behavior (Phase 1):** one flat item per `form add`; unknown fields silently stripped; ≥ 0, types and `null` rejected; several accepted fields never routed (4c, 13, 18, 19, UBIA/SSTB, and 16 foreign tax without K-3); 14A = 0 treated as missing. Details and consequences are in `planning/03`.
- **Resolved in Phase 3:** the $0 tax on the Copperleaf K-1 comes from **Box 9b**, not from K-1-only returns: `rate_28_gain_worksheet` and `qdcgtw` both emit `rate_28_gain`, the engine merges them into an array, and `income_tax_calculation` (then `form6251`) fails Zod validation, reported only as an `[EXECUTOR_NODE_FAILURE]` warning. Worth an upstream issue. Also: `schedule_a` is a singleton (a second entry is ignored, not summed); `form4952` has no input node feeding it; `form update` replaces an entry's data.
- Some engine lines round to whole dollars (refund 8053 vs 8053.20). Comparisons need a tolerance.
- **OpenTax `NOTICE` reserves IRS MeF Software Developer/Transmitter rights** for this codebase to Filed Inc. and its OTTA partners. That's consistent with Phase 8 (export plus `FakeTransmitter` dry run, never submitted), and it's one more reason never to add a real transmission path.
- The synthetic demo runner refuses an existing `--out` dir and writes intermediates to the system temp dir; `intake_k1` should give it a fresh dir per run.

Related announcement links: filed.com/newsroom/open-tax-technology-alliance · filed.com/blog/we-open-sourced-our-tax-engine · accountingtoday.com (Open Tax Technology Alliance launch)
