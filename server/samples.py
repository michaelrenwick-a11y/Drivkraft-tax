"""Bundled synthetic K-1s: the only things intake accepts (ground rule 1).

The upstream PDF runner checks its source hash, so the one PDF sample is the
synthetic package it was built for. The OTD samples skip extraction.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import paths


@dataclass(frozen=True)
class Sample:
    id: str
    kind: str                # pdf | otd
    title: str
    description: str
    path: Path

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "title": self.title, "description": self.description,
                "available": self.path.exists()}


SAMPLES: dict[str, Sample] = {s.id: s for s in [
    Sample("synthetic-k1", "pdf", "Copperleaf Real Estate Fund V",
           "27-page synthetic K-1 package (face + statements) from otd-spec. Runs the full PDF → OTD extraction "
           "with named stages and box-level evidence.",
           paths.OTD_SYNTHETIC / "source" / "synthetic-k1.pdf"),
    Sample("proof-k1", "otd", "OTD round-trip proof K-1",
           "The otd-spec proof document: 70 nodes and 5 statements, no PDF. Good for exercising the bridge.",
           paths.OTD_PROOF),
    Sample("oak-ventures", "otd", "Oak Ventures (benchmark 82)",
           "OTD twin of OpenTax benchmark 82's K-1 (Boxes 1, 2, 5, 6a, 6b, 9a). No PDF.",
           paths.FIXTURES / "bench-82-oak-ventures.otd.yaml"),
]}
