# 03 — OTD → OpenTax K-1 Mapping

Source of truth: `server/bridge/mapping.yaml` (built in Phase 1). This doc explains it.
Upstream versions: OTD taxonomy `irs-k1-1065-2025` v2025.1.1 (`otd-spec@be6452a`) · OpenTax `forms/f1040/nodes/inputs/k1_partnership/index.ts` (`opentax@c4c7d72` = v2.0.4).

## How the engine actually takes a K-1 (verified in Phase 1, 2026-09-25)

- **One flat item per `form add`.** The node schema is a `k1_partnerships` array, but the CLI takes one flat `{partnership_name, box…}` object per call and builds the array itself. Each K-1 is its own `form add` (entries `k1_partnership_01`, `_02`, …).
- **Unknown fields are silently stripped.** `partnership_ein` (used by every upstream benchmark) or a typo like `box_1` is accepted and dropped. So the bridge sends only fields in the engine's own schema, which it reads from `opentax node inspect` at runtime, and refuses anything else.
- **Constraints are enforced**: ≥ 0 fields, types and `null` are all rejected with a Zod error. The bridge checks them first so the reviewer gets a located message, and it omits nulls rather than sending them.
- **Accepted ≠ used.** Reading `index.ts` shows fields the schema accepts but the calculation never routes:
  - `box4c_total_guaranteed_payments`: the engine sums 4a + 4b.
  - `box13_deductions`: `box13DeductionOutputs` returns `[]`. Upstream benchmarks put Box 13 amounts into `schedule_a` directly.
  - `box18_tax_exempt_income`, `box19_distributions`: "no routing needed".
  - `box16_foreign_tax`: routes to Form 1116 only together with `box16_foreign_income` and `_category`, which come from the K-3.
  - `box20_ubia`, `box20_sstb`: Form 8995 gets QBI and W-2 wages only.
- **Zero is treated as missing** in two places. SE earnings use `box14a || box4a`, so a K-1 that says 14A = 0 still gets SE tax on 4a. Box 1 counts as passive NII whenever 14A is absent **or zero**.
- Everything else named below exists and routes as the table says. Other accepted fields (basis, `pre2018_*` carryovers, `box20_aggregation_group`) are preparer inputs, not K-1 face values, so the bridge doesn't set them.

## Dispositions

- **mapped**: 1:1 into an OpenTax field.
- **collapsed**: several OTD codes are summed into one OpenTax field. Per-code detail is lost in the calculation but kept in the ledger.
- **derived**: computed from a statement or text (Box 20 Z, Item B).
- **unsupported**: has a 1040 effect OpenTax can't take. A non-zero value sets `calculation_incomplete`.
- **informational**: no 1040 calculation effect (identifiers, checkboxes, basis-only items).

A field the engine accepts but never routes is **not sent**. Its disposition records what the value really does.

## Part III — boxes

| OTD box | OpenTax field | Disposition | Why |
|---|---|---|---|
| 1, 2, 3, 4a, 4b | `box1_ordinary_business` … `box4b_guaranteed_capital` | mapped | |
| 4c | — | informational | Not routed; the bridge reconciles 4a + 4b = 4c instead |
| 5, 6a, 6b, 6c | `box5_interest` … `box6c_dividend_equivalents` | mapped | ≥ 0 in the engine; a negative is refused, never clamped |
| 7, 8, 9a, 9c, 10 | `box7_royalties` … `box10_net_1231` | mapped | |
| 9b | `box9b_collectibles_gain` | mapped | Not the legacy `box9b_unrecaptured_1250` |
| 11 A, J, R | `box11_other_income` | collapsed | Engine sends it to Schedule 1 line 8z as ordinary income; only ordinary codes are summed |
| 11 other codes | — | unsupported | Capital, §1256, COD (§108 decision), §743(b) and other codes would be misstated as line 8z |
| 12 | `box12_section_179` | mapped | Form 4562 |
| 13 all codes | — | unsupported | Engine ignores `box13_deductions`. A later phase routes A–G to `schedule_a` and H to Form 4952 |
| 14 A | `box14a_se_earnings` | mapped | See "zero is missing" above |
| 14 B, C | — | informational | Gross income used only for the optional SE methods |
| 15 all codes | — | unsupported | No credit inputs on `k1_partnership` |
| 16 | — | informational | K-3 checkbox; OpenTax `box16_*` follows the pre-2021 layout |
| 17 A, B, C, F | `box17_amt_adjustment` | collapsed | Form 6251 other adjustments |
| 17 D, E | — | unsupported | Oil and gas gross income and deductions aren't adjustments |
| 18 A | — | unsupported | Tax-exempt interest belongs on 1040 line 2a (affects Social Security taxability) |
| 18 B, C | — | informational | Basis only. C is never income |
| 19 F | — | unsupported | Taxable portion of property distributed for services |
| 19 other codes | — | informational | Basis only (no basis tracking yet) |
| 20 Z | `box20z_qbi`, `box20_w2_wages`, `box20_ubia`, `box20_sstb` | derived | From the §199A statement. `sstb: true` is **not** sent and is flagged (the engine ignores it, so the deduction would be overstated). Several Z activities are summed and flagged |
| 20 informational codes | — | informational | A, B, E, N, U–Y, AA–AG, AL, AN, AO, AR, AW–AZ: supporting data or only relevant on sale of the interest |
| 20 other codes | — | unsupported | Recapture, look-back interest, §1061, excess business loss, and so on |
| 21 | — | unsupported | Needs K-3 income and category to reach Form 1116 |
| 22 | — | informational | More than one at-risk activity (Form 6198) |
| 23 | — | informational | "More than one activity for passive purposes." It does **not** state passive status, so it can't be compared with the engine's inference; see the `passive_inferred` flag |

## Parts I–II

| OTD | OpenTax | Disposition |
|---|---|---|
| Item B partnership name/address | `partnership_name` (required) | derived: first line; for a one-line value, the text before the first part that starts with a digit |
| Item A EIN, Item E partner TIN | — | informational; **redacted** in the ledger |
| Item K1 liabilities | — | informational; feeds basis in a later phase |
| Item L capital account | — | informational. **Not** outside basis; never feed `basis_beginning` |
| Everything else | — | informational |

## What the bridge enforces (`server/bridge/translator.py`)

1. **Validation gate.** The upstream `validate_otd.validate()` runs in a subprocess. An invalid document is refused, with the error located to its OTD path. The taxonomy id and version must match `mapping.yaml`.
2. **Full coverage.** Every node, code and statement field becomes a ledger entry. A node or code with no rule refuses the document. Tests check that every live taxonomy code resolves to a rule.
3. **null ≠ 0.** A null is omitted and a 0 is sent. Unverified values (`_unverified`) are flagged.
4. **Engine constraints before the engine.** Allowlist, types and ≥ 0 are checked against the live engine schema. A violation refuses the document with a located error.
5. **Reconciliation.** Each sent field equals the sum of its routed ledger entries. Each Part III box has the same entry count and total in the ledger as in the OTD. The bridge also checks 4a + 4b = 4c and 6b ≤ 6a; upstream validation catches both first, so these are defense in depth.
6. **Flags** (don't block): `calculation_incomplete` (a non-zero unsupported value), `unverified_value` / `human_review`, `engine_overrides_zero` (14A = 0 and 4a > 0), `engine_se_fallback`, `passive_inferred`, `multiple_199a_activities`, `statement_review` (a statement with no amount, e.g. 20 ZZ Form 926).

Goldens: `server/tests/golden/{proof,synthetic,bench-82}.bridge.json`. `bench-82` is a synthetic OTD built from OpenTax benchmark 82's K-1 (`server/tests/fixtures/build_bench_fixtures.py`). Swapped into that benchmark, it reproduces the expected total tax, refund and amount owed within $5.

## Upstream issues worth raising (optional)

- `box13_deductions`, `box18_tax_exempt_income` and `box19_distributions` are accepted but never routed. Either route them or drop them from the schema.
- Unknown input fields are stripped silently. Make this a strict schema, or at least warn.
- A 14A of 0 is treated as missing (SE fallback to 4a, and passive inference for Box 1). Propose `??` instead of `||`-style checks and an explicit material-participation input.
- `box11_other_income` sends every code to line 8z. Propose per-code inputs (at least C, E and S).
- `box20_sstb` and `box20_ubia` are unused. There's no 8995-A path above the threshold.
- Box 16 fields follow the pre-2021 layout. Propose a Box 21 + K-3 model.
- No Box 15 credit routing and no Box 20 routing beyond Code Z.

### MeF export (found in Phase 8, 2026-09-26)

- `taxpayer_prior_year_agi` is read into the filer identity but never written as `PrimaryPriorYearAGIAmt`, so a self-select PIN can't be verified. The dry run adds the element to the signed XML itself.
- `return validate` evaluates every rule, including rules for forms the return doesn't contain (50 rejects on one case, where `return export` counts 10). Scope validation to the forms present.
- IND-082 is implemented as `OwedAmt == RefundAmt`, so every balance-due return fails it.
- Schedule A is emitted even when the standard deduction wins, which trips F1040-021-03.
- Form 8960 is emitted without its totals (F8960-007/008-01/010) and without `FilingThresholdAmt` (F8960-023).
- F1040-018-01 (ordinary dividends vs. Schedule B) fails even when both carry the same amount.
- A W-2 without employer EIN or address stops the whole export with a plain-text error (one field at a time), not a rule finding.
