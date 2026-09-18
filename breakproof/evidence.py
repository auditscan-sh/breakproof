"""Finding types. Dumb data, no opinions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Verdict(str, Enum):
    REQUIRED = "REQUIRED"
    NECESSARY = "NECESSARY"
    UNNECESSARY = "UNNECESSARY"
    DEAD = "DEAD"
    UNREACHABLE = "UNREACHABLE"
    MISSING = "MISSING"
    INCORRECT = "INCORRECT"
    REDUNDANT = "REDUNDANT"
    RISKY = "RISKY"
    EXPENSIVE = "EXPENSIVE"
    REGRESSION = "REGRESSION"
    UNPROVEN = "UNPROVEN"
    UNKNOWN = "UNKNOWN"


@dataclass
class Evidence:
    kind: str
    summary: str
    detail: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {"kind": self.kind, "summary": self.summary, "detail": self.detail}


@dataclass
class Finding:
    id: str
    title: str
    verdict: Verdict
    severity: str
    location: Optional[Dict] = None
    requirement_id: Optional[str] = None
    claim: str = ""
    static_evidence: List[Evidence] = field(default_factory=list)
    runtime_evidence: List[Evidence] = field(default_factory=list)
    counterfactual: Optional[Evidence] = None
    confidence: float = 0.0

    def add(self, ev: Evidence) -> None:
        if ev.kind == "runtime":
            self.runtime_evidence.append(ev)
        elif ev.kind == "counterfactual":
            self.counterfactual = ev
        else:
            self.static_evidence.append(ev)
        self._recompute_confidence()

    def _recompute_confidence(self) -> None:
        score = 0.0
        if self.static_evidence:
            score += 0.4
        if self.runtime_evidence:
            score += 0.3
        if self.counterfactual is not None:
            score += 0.3
        self.confidence = min(1.0, score)

    def as_dict(self) -> Dict:
        return {
            "id": self.id, "title": self.title, "verdict": self.verdict.value,
            "severity": self.severity, "location": self.location,
            "requirement_id": self.requirement_id, "claim": self.claim,
            "static_evidence": [e.as_dict() for e in self.static_evidence],
            "runtime_evidence": [e.as_dict() for e in self.runtime_evidence],
            "counterfactual": self.counterfactual.as_dict() if self.counterfactual else None,
            "confidence": round(self.confidence, 3),
        }


class EvidenceEngine:
    """Mints findings. That's it."""

    def new(self, *, id: str, title: str, verdict: Verdict, severity: str,
            location: Optional[Dict] = None, requirement_id: Optional[str] = None,
            claim: str = "") -> Finding:
        return Finding(id=id, title=title, verdict=verdict, severity=severity,
                       location=location, requirement_id=requirement_id, claim=claim)

    def finalize(self, f: Finding) -> Finding:
        strong = f.verdict in (Verdict.NECESSARY, Verdict.REGRESSION)
        if strong and f.confidence < 0.6:
            f.verdict = Verdict.UNPROVEN
        return f
