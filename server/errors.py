"""Structured tool errors: {code, message, fix_hint} (planning/04, "Conventions").

Every anticipated failure is a `ToolFailure`. The MCP adapter turns it into a
tool error the model can read; the HTTP adapter turns it into a 4xx JSON body.
"""
from __future__ import annotations

from typing import Any

# One hint per bridge issue code, written for the person (or model) who has to fix it.
FIX_HINTS: dict[str, str] = {
    # Refusals (block approval)
    "validator_error": "The upstream OTD validator couldn't run. Re-run scripts/bootstrap.sh, then retry.",
    "otd_invalid": "Open the path named in the error and correct the value with edit_k1_value; the document re-validates on save.",
    "taxonomy_mismatch": "This K-1 uses a taxonomy version the mapping doesn't cover. Re-extract it with the pinned otd-spec.",
    "unknown_node": "The document has a node the taxonomy doesn't define. Re-extract it; the bridge never guesses a mapping.",
    "no_mapping_rule": "No rule covers this box or code yet. Add one to server/bridge/mapping.yaml (and a test) before bridging.",
    "not_numeric": "Replace the value at this path with a number (edit_k1_value).",
    "field_collision": "Two boxes feed the same engine field. Check the K-1 for a duplicated entry and remove one.",
    "field_not_in_engine": "mapping.yaml names a field the pinned OpenTax doesn't accept. Fix the mapping or the version pin.",
    "engine_type": "The value has the wrong type for the engine field. Correct it with edit_k1_value.",
    "engine_constraint": "OpenTax requires this amount to be ≥ 0. Check the sign on the K-1 and correct it; nothing is clamped.",
    "missing_partnership_name": "Enter the partnership's name at part_i.item_b with edit_k1_value.",
    "ledger_mismatch": "The ledger didn't reconcile to the OTD. This is a bridge bug: keep the document and report it.",
    "k1_arithmetic": "The K-1's own arithmetic doesn't hold. Compare the boxes named with the PDF and fix the misread one.",
    # Flags (don't block)
    "calculation_incomplete": "Acknowledge it before approval: this amount won't reach the 1040 until a later phase routes it.",
    "unverified_value": "Compare the value with its PDF highlight. Editing it (even to the same value) marks it verified.",
    "human_review": "The extractor asked for a human look. Compare with the PDF and edit if it's wrong.",
    "engine_overrides_zero": "OpenTax will compute SE tax on Box 4a anyway. Note it in the file; an upstream issue is open.",
    "engine_se_fallback": "No Box 14 A, so OpenTax uses Box 4a for SE earnings. Confirm that's right for this partner.",
    "passive_inferred": "Confirm the partner's material participation; OpenTax assumes passive when 14 A is empty or zero.",
    "multiple_199a_activities": "QBI from several §199A activities was summed. Check the statement if they need separate treatment.",
    "deduction_sign_normalized": "Confirm the K-1 shows this as a deduction (parentheses). If it's really a negative deduction, edit it with a reason.",
    "agi_limit_simplified": "OpenTax applies one charitable AGI limit. If total gifts are near 30% of AGI, check the 30%/20% limits by hand.",
    "investment_interest_unlimited": "Form 4952 isn't applied: confirm net investment income covers this interest, or reduce it with edit_k1_value and a reason.",
    "statement_review": "Read the attached statement on the PDF; it carries information but no amount.",
}


class ToolFailure(Exception):
    """An anticipated, structured tool error."""

    def __init__(self, code: str, message: str, fix_hint: str = "", *, status: int = 400, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix_hint = fix_hint or FIX_HINTS.get(code, "")
        self.status = status
        self.detail = detail

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message, "fix_hint": self.fix_hint}
        if self.detail is not None:
            d["detail"] = self.detail
        return d


def not_found(kind: str, ident: str, hint: str) -> ToolFailure:
    return ToolFailure(f"{kind}_not_found", f"No {kind} with id {ident!r}", hint, status=404)


def with_hint(issue: dict) -> dict:
    """A bridge issue dict with its fix_hint added."""
    return {**issue, "fix_hint": FIX_HINTS.get(issue["code"], "")}
