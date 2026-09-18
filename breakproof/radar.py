"""Diff two frozen endpoint contracts. Removed routes break; added ones don't.

That's the whole philosophy. Everything else is bookkeeping.
"""

from __future__ import annotations

from typing import Dict, List

from breakproof.evidence import Evidence, EvidenceEngine, Finding, Verdict

# "X consumes Y's API" edges. Deploy wiring and imports don't count —
# refactors aren't breakages, no matter how scary the diff looks.
CALLER_KINDS = ("calls", "publish", "subscribe", "event")

MAX_BREAK_FINDINGS = 25
MAX_WATCH_ROWS = 50


def normalize_path(path: str) -> str:
    path = (path or "").strip() or "/"
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1:
        path = path.rstrip("/")
    return path


def break_key(method: str, path: str) -> str:
    """Stable cross-scan identity for one contract (also the finding id)."""
    return f"API-{(method or 'GET').upper()}-{normalize_path(path)}"


def normalize_endpoints(endpoints) -> Dict[str, Dict]:
    """Index endpoint records by contract identity (deterministic)."""
    out: Dict[str, Dict] = {}
    for ep in endpoints or []:
        if not isinstance(ep, dict):
            continue
        method = str(ep.get("method", "GET") or "GET").upper()
        proto = str(ep.get("protocol", "http") or "http").lower()
        path = normalize_path(ep.get("path", ""))
        key = break_key(method, path)
        if key not in out:
            out[key] = {"key": key, "protocol": proto, "method": method,
                        "path": path,
                        "service": str(ep.get("service", "") or ""),
                        "handler": str(ep.get("handler", "") or ""),
                        "file": str(ep.get("file", "") or ""),
                        "line": ep.get("line", "") or ""}
    return out


def api_contract(svc_summary) -> Dict:
    """Trimmed contract snapshot (endpoints + call edges)."""
    summary = svc_summary if isinstance(svc_summary, dict) else {}
    indexed = normalize_endpoints(summary.get("endpoints"))
    endpoints = [indexed[key] for key in sorted(indexed)]
    edges = []
    for e in summary.get("edges", []) or []:
        if not isinstance(e, dict):
            continue
        edges.append({"src": str(e.get("src") or e.get("from") or ""),
                      "dst": str(e.get("dst") or e.get("to") or ""),
                      "kind": str(e.get("kind") or e.get("type") or ""),
                      "file": str(e.get("file", "") or ""),
                      "line": e.get("line", "") or ""})
    return {"endpoints": endpoints, "edges": edges}


def _callers(prev_edges, owner: str) -> List[Dict]:
    if not owner:
        return []
    out = []
    for e in prev_edges or []:
        if e.get("kind") not in CALLER_KINDS or e.get("dst") != owner:
            continue
        out.append({"service": e.get("src", ""),
                    "file": e.get("file", ""), "line": e.get("line", ""),
                    "via": e.get("kind", "calls")})
    out.sort(key=lambda c: (c["service"], str(c["file"]), str(c["line"])))
    return out


def build_api_diff(prev_contract=None, curr_contract=None) -> Dict:
    """Diff two frozen contracts. Pure, deterministic, sorted."""
    prev = prev_contract if isinstance(prev_contract, dict) else {}
    curr = curr_contract if isinstance(curr_contract, dict) else {}
    prev_eps = normalize_endpoints(prev.get("endpoints"))
    curr_eps = normalize_endpoints(curr.get("endpoints"))
    prev_edges = [e for e in (prev.get("edges") or []) if isinstance(e, dict)]
    curr_triples = {(e.get("src"), e.get("dst"), e.get("kind"))
                    for e in (curr.get("edges") or []) if isinstance(e, dict)}

    removed, added = [], []
    for key in sorted(set(prev_eps) - set(curr_eps)):
        rec = dict(prev_eps[key])
        rec["callers"] = _callers(prev_edges, rec["service"])
        removed.append(rec)
    for key in sorted(set(curr_eps) - set(prev_eps)):
        added.append(dict(curr_eps[key]))

    changed = []
    for proto, path in sorted({(r["protocol"], r["path"]) for r in
                               list(prev_eps.values()) + list(curr_eps.values())}):
        before = sorted(v["method"] for v in prev_eps.values()
                        if v["protocol"] == proto and v["path"] == path)
        after = sorted(v["method"] for v in curr_eps.values()
                       if v["protocol"] == proto and v["path"] == path)
        dropped = [m for m in before if m not in after]
        gained = [m for m in after if m not in before]
        if dropped or gained:
            still = [m for m in before if m in after]
            if still:
                owner = next((v["service"] for v in curr_eps.values()
                              if v["protocol"] == proto and v["path"] == path), "")
                changed.append({"protocol": proto, "path": path,
                                "removed_methods": dropped,
                                "added_methods": gained,
                                "breaking": bool(dropped),
                                "service": owner,
                                "callers": _callers(prev_edges, owner)})

    watch = []
    for e in prev_edges:
        if e.get("kind") not in CALLER_KINDS:
            continue
        if (e.get("src"), e.get("dst"), e.get("kind")) not in curr_triples:
            watch.append({"src": e.get("src", ""), "dst": e.get("dst", ""),
                          "kind": e.get("kind", ""), "file": e.get("file", ""),
                          "line": e.get("line", "")})
    watch.sort(key=lambda w: (w["src"], w["dst"], w["kind"]))
    watch = watch[:MAX_WATCH_ROWS]

    return {"removed": removed, "added": added, "changed": changed,
            "watch": watch,
            "summary": {"removed": len(removed), "added": len(added),
                        "changed": len(changed), "watch": len(watch),
                        "breaking": len(removed)}}


def api_break_findings(diff: Dict | None, prev_job_id: str,
                       ev: EvidenceEngine) -> List[Finding]:
    """One RISKY/high finding per removed endpoint (never double-filed)."""
    diff = diff if isinstance(diff, dict) else {}
    prev_job = (prev_job_id or "")[:12]
    targets = []
    for rec in diff.get("removed", []) or []:
        if isinstance(rec, dict):
            targets.append((rec.get("key") or break_key(rec.get("method"), rec.get("path")),
                            rec))
    targets.sort(key=lambda t: t[0])
    findings: List[Finding] = []
    for key, rec in targets[:MAX_BREAK_FINDINGS]:
        callers = rec.get("callers") or []
        first = next((c for c in callers if c.get("file")), None)
        location = ({"file": first["file"], "line": first.get("line") or 0,
                     "col": 0, "end_line": 0, "end_col": 0}
                    if first else {})
        caller_note = (f"Affected callers: "
                       + ", ".join(f"{c['service']} ({c.get('file', '?')}"
                                   f"{':' + str(c['line']) if c.get('line') else ''})"
                                   for c in callers[:8]) if callers
                       else "No in-repo callers observed — external consumers may still break.")
        f = ev.new(
            id=key,
            title=f"Breaking API change: {rec.get('method')} {rec.get('path')} vanished",
            verdict=Verdict.RISKY, severity="high", location=location,
            claim=(f"Contract {rec.get('method')} {rec.get('path')} served by "
                   f"'{rec.get('service') or 'unknown service'}' in scan {prev_job} "
                   f"is gone. {caller_note}"))
        f.add(Evidence("static", "Route present in previous frozen scan, absent now.",
                       {"contract": key, "previous_job": prev_job_id,
                        "owner": rec.get("service", ""),
                        "callers": callers[:20]}))
        f.add(Evidence("counterfactual", "Restore the route or migrate every caller, then re-scan.",
                       {"fix": f"restore {rec.get('method')} {rec.get('path')}"}))
        findings.append(ev.finalize(f))
    return findings


def render_radar_markdown(diff: Dict | None, job_id: str = "") -> str:
    """Shareable contract-diff rendering (findings only for breakage)."""
    d = diff if isinstance(diff, dict) else {}
    s = d.get("summary", {}) or {}
    lines = [
        "# API Change Radar",
        "",
        f"Scan: `{(job_id or '')[:12]}` — breaking changes: {s.get('breaking', 0)} "
        f"(removed {s.get('removed', 0)}, method-breaks "
        f"{sum(1 for c in d.get('changed', []) or [] if c.get('breaking'))}, "
        f"added {s.get('added', 0)})",
        "",
        "## Removed contracts (breaking)",
    ]
    for rec in d.get("removed", []) or []:
        callers = ", ".join(c["service"] for c in rec.get("callers", [])[:6]) or "none observed"
        lines.append(f"- **{rec.get('method')} {rec.get('path')}** "
                     f"(was: {rec.get('service', '?')}; callers: {callers})")
    if not (d.get("removed", []) or []):
        lines.append("- None.")
    lines.append("")
    lines.append("## Changed method-sets")
    for ch in d.get("changed", []) or []:
        mark = "BREAKING" if ch.get("breaking") else "compatible"
        lines.append(f"- {ch.get('path')} [{mark}]: "
                     f"dropped {', '.join(ch.get('removed_methods', [])) or '—'}; "
                     f"gained {', '.join(ch.get('added_methods', [])) or '—'}")
    if not (d.get("changed", []) or []):
        lines.append("- None.")
    lines.append("")
    lines.append("## Added contracts (informational)")
    for rec in (d.get("added", []) or [])[:20]:
        lines.append(f"- {rec.get('method')} {rec.get('path')} ({rec.get('service', '?')})")
    if not (d.get("added", []) or []):
        lines.append("- None.")
    lines.append("")
    lines.append("## Watch: vanished consumption (informational, not flagged)")
    for w in (d.get("watch", []) or [])[:20]:
        lines.append(f"- {w.get('src')} no longer {w.get('kind')} {w.get('dst')}")
    if not (d.get("watch", []) or []):
        lines.append("- None.")
    return "\n".join(lines)
