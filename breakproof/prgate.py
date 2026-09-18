"""Gate a PR: fail on removals, new CVEs, new secrets. Everything else passes.

Additions never fail. Yes, really.
"""

from __future__ import annotations

from typing import Dict

from breakproof.radar import build_api_diff


def affected_cves(statements) -> set:
    return {str(s.get("cve") or "").upper()
            for s in (statements or []) if isinstance(s, dict)
            and (s.get("state") or "") == "affected" and s.get("cve")}


def secret_sites(compliance_controls) -> set:
    out = set()
    for c in compliance_controls or []:
        if not isinstance(c, dict) or c.get("status") != "fail":
            continue
        if c.get("id") not in ("C-SECRETS", "C-CFG-SECRETS"):
            continue
        for e in c.get("evidence") or []:
            if isinstance(e, dict) and e.get("file"):
                out.add((str(e.get("file")), str(e.get("line", ""))))
    return out


def build_gate(base_contract=None, head_contract=None, base_affected=None,
               head_affected=None, base_secrets=None, head_secrets=None,
               base_ref: str = "", head_ref: str = "") -> Dict:
    """PR verdict from frozen contracts + advisory/secret sets. Deterministic."""
    diff = build_api_diff(
        base_contract if isinstance(base_contract, dict) else {},
        head_contract if isinstance(head_contract, dict) else {})
    new_cves = sorted(set(head_affected or ()) - set(base_affected or ()))
    new_secrets = sorted(set(head_secrets or ()) - set(base_secrets or ()))
    breaking = (diff.get("summary") or {}).get("breaking", 0)
    failed = bool(breaking or new_cves or new_secrets)
    return {
        "verdict": "fail" if failed else "pass",
        "base_ref": base_ref or "",
        "head_ref": head_ref or "",
        "diff": diff,
        "new_cves": [{"cve": c} for c in new_cves],
        "new_secrets": [{"file": f, "line": ln} for f, ln in new_secrets],
        "summary": {"breaking": breaking,
                    "removed": (diff.get("summary") or {}).get("removed", 0),
                    "new_cves": len(new_cves),
                    "new_secrets": len(new_secrets)},
    }


def render_gate_markdown(gate: Dict | None) -> str:
    """CI-readable verdict rendering."""
    g = gate if isinstance(gate, dict) else {}
    s = g.get("summary", {}) or {}
    verdict = str(g.get("verdict", "pass")).upper()
    lines = [
        f"# PR Merge Gate: {verdict}",
        "",
        f"Base: `{g.get('base_ref', '')}` → Head: `{g.get('head_ref', '')}`",
        f"Breaking contracts: {s.get('breaking', 0)} · "
        f"New CVEs: {s.get('new_cves', 0)} · "
        f"New secret sites: {s.get('new_secrets', 0)}",
        "",
        "## Removed contracts (breaking)",
    ]
    for rec in (g.get("diff") or {}).get("removed", []) or []:
        callers = ", ".join(c.get("service", "") for c in rec.get("callers", [])[:6])
        lines.append(f"- **{rec.get('method')} {rec.get('path')}** "
                     f"(was: {rec.get('service', '?')}; callers: {callers or 'none observed'})")
    if not ((g.get("diff") or {}).get("removed", []) or []):
        lines.append("- None.")
    lines.append("")
    lines.append("## New reachable CVEs")
    for item in g.get("new_cves", []) or []:
        lines.append(f"- {item.get('cve')}")
    if not (g.get("new_cves", []) or []):
        lines.append("- None.")
    lines.append("")
    lines.append("## New secret sites")
    for item in g.get("new_secrets", []) or []:
        lines.append(f"- {item.get('file')}:{item.get('line')}")
    if not (g.get("new_secrets", []) or []):
        lines.append("- None.")
    return "\n".join(lines)
