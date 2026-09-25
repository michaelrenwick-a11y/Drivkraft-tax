# 03 — OTD → OpenTax K-1 Mapping

Source of truth once built: `server/bridge/mapping.yaml`. This doc is the design for it.
Upstream versions: OTD taxonomy `irs-k1-1065-2025` v2025.1.1 (`otd-spec@be6452a`) · OpenTax `forms/f1040/nodes/inputs/k1_partnership/index.ts` (`opentax@c4c7d72` = v2.0.4).

**Checked against the v2.0.4 binary (2026-09-25, `opentax node inspect --node_type k1_partnership`)**: every OpenTax field named below exists. The input is a `k1_partnerships` array (min 1), one item per K-1. The engine also accepts fields this doc doesn't map yet:
- `box20_aggregation_group` (string): the likely hook for multiple §199A activities in Box 20 Z; use it before flagging "> 1 activity".
- `box16_foreign_income`, `box16_foreign_income_category`, `box16_foreign_deductions`: stay unset until K-3 (see Box 21).
- Basis: `basis_contributions`, `basis_share_of_income`, `basis_share_of_losses`, `basis_liabilities_assumed/relieved`, plus `basis_beginning`/`basis_distributions`. These are preparer inputs, not K-1 face values (Item L is not basis).
- Suspended losses: `pre2018_basis_*` and `pre2018_atrisk_*` (ordinary, ST/LT capital, other). These are prior-year carryovers, not K-1 values, so they're out of scope for the bridge.

Output nodes it feeds: schedule1, schedule_b, schedule_d, schedule_se, form8995, form_1116, form6251, form8960, form4797, form4562, the unrecaptured-1250 and 28%-rate worksheets, and f1040.

To verify in Phase 1: benchmark `93-mfj-w2-k1` sends a flat `{partnership_name, partnership_ein}` object rather than the array, and `partnership_ein` isn't in the schema. Confirm whether the CLI wraps or strips these, and whether unknown fields are silently dropped. If they are, the bridge must reject them itself (the OTD discipline: never drop anything silently).

Disposition values:
- **mapped**: 1:1 into an OpenTax field.
- **collapsed**: several OTD codes are summed into one OpenTax field, so per-code detail is lost in the calculation (it stays in the ledger).
- **derived**: computed from an OTD statement or from several nodes.
- **unsupported**: OpenTax has no input for it. Ledgered and flagged to the reviewer.
- **informational**: no tax effect in the 1040 calculation, e.g. identifiers and checkboxes.

## Part III — boxes

| OTD box | OTD `semantic_id` | OpenTax field | Disposition | Notes |
|---|---|---|---|---|
| 1 | `ordinary_business_income` | `box1_ordinary_business` | mapped | |
| 2 | `net_rental_real_estate_income` | `box2_rental_re` | mapped | |
| 3 | `other_net_rental_income` | `box3_other_rental` | mapped | |
| 4a | `guaranteed_payments_services` | `box4a_guaranteed_services` | mapped | |
| 4b | `guaranteed_payments_capital` | `box4b_guaranteed_capital` | mapped | |
| 4c | `guaranteed_payments_total` | `box4c_total_guaranteed_payments` | mapped | Reconcile: 4a + 4b = 4c |
| 5 | `interest_income` | `box5_interest` | mapped | OpenTax requires ≥ 0; a negative is an error, not a clamp |
| 6a | `ordinary_dividends` | `box6a_ordinary_dividends` | mapped | ≥ 0 |
| 6b | `qualified_dividends` | `box6b_qualified_dividends` | mapped | ≤ 6a check |
| 6c | `dividend_equivalents` | `box6c_dividend_equivalents` | mapped | |
| 7 | `royalties` | `box7_royalties` | mapped | |
| 8 | `net_short_term_capital_gain` | `box8_net_st_cap_gain` | mapped | |
| 9a | `net_long_term_capital_gain` | `box9a_net_lt_cap_gain` | mapped | |
| 9b | `collectibles_gain` | `box9b_collectibles_gain` | mapped | **Don't** use the OpenTax legacy field `box9b_unrecaptured_1250` |
| 9c | `unrecaptured_section_1250_gain` | `box9c_unrecaptured_1250` | mapped | |
| 10 | `net_section_1231_gain` | `box10_net_1231` | mapped | |
| 11 A–ZZ | `other_income` (coded) | `box11_other_income` | **collapsed** | Codes route differently (e.g. C §1256 → Form 6781, E COD income, F §743(b)). One number loses that. Ledger each code; flag codes that need special routing |
| 12 | `section_179_deduction` | `box12_section_179` | mapped | Needs basis/limit context; Form 4562 |
| 13 A–ZZ | `other_deductions` (coded) | `box13_deductions` | **collapsed** | OpenTax takes one number ≥ 0. Code A charitable (Sch A), H investment interest (Form 4952), L portfolio deductions (nondeductible post-TCJA) and others land in different places, and some shouldn't be summed at all. **Highest-risk collapse.** v1: sum only codes the mapping marks `summable`; all others unsupported + flag |
| 14 A | `self_employment` code A | `box14a_se_earnings` | mapped | |
| 14 B | code B (farming) | — | unsupported | |
| 14 C | code C (gross nonfarm) | — | unsupported | Needed for the optional method |
| 15 A–AN | `credits` (coded) | — | **unsupported** | No credit inputs on `k1_partnership`. Some credits have their own OpenTax nodes (e.g. `f3800`, `f8582cr`); a later mapping can route them there |
| 16 | `international_transactions` (reference → K-3) | — | informational | In the 2025 form Box 16 is the "K-3 attached" checkbox. OpenTax's `box16_*` fields describe the **pre-2021 layout**; see Box 21 |
| 17 A–F | `amt_items` (coded) | `box17_amt_adjustment` | collapsed | Net of codes; sign preserved |
| 18 A–C | `tax_exempt_nondeductible` (coded) | `box18_tax_exempt_income` | collapsed (A+B only) | Code C (nondeductible expenses) → basis only, not income. Must **not** be summed into 18 |
| 19 A–G | `distributions` (coded) | `box19_distributions` | collapsed | Also feeds `basis_distributions` if basis tracking is on |
| 20 Z | `other_information.section_199a` + statement | `box20z_qbi`, `box20_w2_wages`, `box20_ubia`, `box20_sstb` | **derived** | From statement `content.qbi / w2_wages / ubia / sstb`. Multiple activities → needs per-activity handling (OpenTax takes one set per K-1). Flag if > 1 |
| 20 other codes | `other_information` | — | unsupported / informational | e.g. A investment income, B investment expenses (Form 4952), N §163(j), AJ excess business loss. Ledger all |
| 21 | `foreign_taxes_paid_accrued` | `box16_foreign_tax` | mapped (renamed) | OpenTax's legacy name. Foreign income/category/deductions come from **K-3**, which isn't implemented → leave `box16_foreign_income*` unset and flag |
| 22 | `at_risk_activities` | — | informational | OpenTax doesn't take it. Needed for Form 6198 |
| 23 | `passive_activities` | — | informational | **OpenTax guesses passive status from whether box14a is present** (`index.ts` ~L300–330). This can disagree with the partner's actual material-participation status. Flag every K-1 where Box 23 and the OpenTax guess disagree |

## Parts I–II and Items

| OTD | OpenTax | Disposition |
|---|---|---|
| Part I Item B partnership name | `partnership_name` (required, non-empty) | derived (first line of name/address) |
| Part I Item A EIN, Part II partner TIN | — | informational; **redacted** in logs/exports |
| Item K liabilities (recourse / QNR / nonrecourse) | `basis_liabilities_assumed/relieved` (year-over-year delta) | derived; Phase 4 basis tracking only |
| Item L capital account | — | informational. **Not** outside basis; never feed it to `basis_beginning` |
| Item M, N, and others | — | informational |

## Reconciliation rules (bridge must enforce)

1. For each numeric box, the OTD value equals the sum of ledger entries attributed to it (mapped + collapsed + unsupported).
2. OTD `null` → field omitted. OTD `0` → field `0`.
3. OpenTax schema constraints (≥ 0 fields) are checked *before* the engine call. On a violation the bridge refuses with a located error; it never clamps.
4. Any `unsupported` entry with a non-null value sets the document flag `calculation_incomplete`, shown in red in the Desk and the impact view.

## Upstream issues worth raising (optional)

- OpenTax `k1_partnership` collapses coded Boxes 11, 13, 17, 18 and 19. Propose per-code inputs.
- OpenTax Box 16 fields follow the pre-2021 layout. Propose a Box 21 + K-3 model.
- Passive status is inferred from box14a. Propose an explicit material-participation input.
- There's no Box 15 credit routing and no Box 20 routing beyond Code Z.
