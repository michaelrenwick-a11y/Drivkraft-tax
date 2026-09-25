# Upstream Pins

| Project | Repo | Pinned commit | License | Read on |
|---|---|---|---|---|
| OTD spec | https://github.com/opentaxdocument/otd-spec | `be6452a` (2026-09-21) | CC BY 4.0 | 2026-09-25 |
| OpenTax engine | https://github.com/filedcom/opentax | `c4c7d72` (2026-09-24) = release **v2.0.4** | AGPL v3 / commercial | 2026-09-25 |

Fetch with `scripts/bootstrap.sh` (needs git, curl, [uv](https://docs.astral.sh/uv/)). It clones both pins into `vendor/`, downloads the `opentax-<os>-<arch>` release binary for v2.0.4 into `vendor/bin/opentax`, and creates `.venv` (Python 3.11) with the OTD demo requirements (`ruamel.yaml`, `simplejson`, `PyYAML`, `pdfplumber`, `pypdf`). Then run `scripts/smoke.sh`.

Key upstream paths:
- OTD taxonomy: `taxonomies/irs-k1-1065-2025.yaml`
- OTD validator: `skills/k1-otd/scripts/validate_otd.py`
- OTD fixtures: `proof/proof-emitted.otd.yaml`, `examples/k1-1065-2025-synthetic/`, `tests/fixtures/hostile-k1/`
- OpenTax K-1 input: `forms/f1040/nodes/inputs/k1_partnership/index.ts`
- OpenTax K-1 benchmarks: `benchmark/cases/f1040/2025/93-mfj-w2-k1/`, `95-single-w2-k1-1099r-1099int-1099div-1099b/`

## Upstream verification results

**2026-09-25, `scripts/smoke.sh`: 4/4 pass** (macOS arm64, Python 3.11.16, opentax 2.0.4). Upstream checkouts stay clean after the run.

| Test | Result | Notes |
|---|---|---|
| OTD round-trip proof (`proof/otd_round_trip_proof.py`) | PASS | 70 indexed nodes, 5 statements; all 5 selected constraints pass |
| `validate_otd.py --input proof/proof-emitted.otd.yaml` | PASS | 0 errors, 0 warnings, 0 unverified |
| Synthetic PDF → OTD (`examples/k1-1065-2025-synthetic/run_demo.py`) | PASS | 27-page synthetic PDF; 52 face fields projected (39 present, 9 verified-absent, 4 blank, 1 missing). Bounded claim: `full_source_document_extraction: false`, `all_source_detail_records_reconciled: false` |
| OpenTax benchmark `93-mfj-w2-k1` via CLI | PASS | Total tax 10,068.18, refund 8,053 (expected 8,053.20), owed 0; same $5 rule as upstream `run_benchmark.ts` |

Things learned that matter for later phases:
- **OpenTax stores state in `./.state/returns` relative to the cwd.** The server must run it from a per-case working dir (e.g. `data/cases/<id>/calc/`), never the repo root.
- **CLI flow:** `return create --year` → `form add --node_type <type> '<json>'` per form → `return get --json` returns `summary` (7 headline lines) plus `lines` (per-line values, often `[value, value]` arrays) and `forms` (active nodes). Also `return validate` (MeF rules) and `return export --type mef|pdf` for Phase 8.
- **The `93-mfj-w2-k1` benchmark K-1 carries no amounts**, only `partnership_name`/`partnership_ein`, and `correct.json` has `k1_ordinary: 0`. It proves the node plumbing, not K-1 math. Phase 3's "reproduce the benchmark through OTD" needs a K-1 with real figures; check `95-single-w2-k1-…` and inspect `opentax node inspect --node_type k1_partnership` during Phase 1.
- Some engine lines round to whole dollars (refund 8053 vs 8053.20). Comparisons need a tolerance.
- **OpenTax `NOTICE` reserves IRS MeF Software Developer/Transmitter rights** for this codebase to Filed Inc. and its OTTA partners. That's consistent with Phase 8 (export plus `FakeTransmitter` dry run, never submitted), and it's one more reason never to add a real transmission path.
- The synthetic demo runner refuses an existing `--out` dir and writes intermediates to the system temp dir; `intake_k1` should give it a fresh dir per run.

Related announcement links: filed.com/newsroom/open-tax-technology-alliance · filed.com/blog/we-open-sourced-our-tax-engine · accountingtoday.com (Open Tax Technology Alliance launch)
