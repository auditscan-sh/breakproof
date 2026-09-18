"""breakproof CLI. Reads a lot, writes only what you point it at.

Exit codes: 0 pass, 1 fail (something broke), 2 you broke the invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from breakproof import __version__
from breakproof.extract import scan_path
from breakproof.prgate import build_gate, render_gate_markdown
from breakproof.radar import build_api_diff, render_radar_markdown

MAX_CONTRACT_BYTES = 50_000_000


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_force_utf8()


def _load_contract(source: str) -> dict:
    if not isinstance(source, str) or not source:
        raise ValueError("empty contract source")
    if os.path.isdir(source):
        return scan_path(source)
    try:
        if os.path.getsize(source) > MAX_CONTRACT_BYTES:
            raise ValueError(f"contract file too large: {source}")
    except OSError as exc:
        raise ValueError(f"cannot read contract: {exc}") from exc
    try:
        with open(source, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ValueError(f"bad contract JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("endpoints"), list):
        return {"endpoints": [], "edges": []}
    edges = data.get("edges") if isinstance(data.get("edges"), list) else []
    return {"endpoints": data["endpoints"], "edges": edges}


def _write_file(path: str, content: str) -> None:
    """Write exactly one file the user named. Nothing else. Ever."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _cmd_scan(args) -> int:
    try:
        contract = scan_path(args.path, service=args.service or "")
    except ValueError as exc:
        print(f"breakproof: {exc}", file=sys.stderr)
        return 2
    payload = json.dumps(contract, indent=2, sort_keys=True) + "\n"
    if args.out:
        try:
            _write_file(args.out, payload)
        except OSError as exc:
            print(f"breakproof: cannot write {args.out}: {exc}", file=sys.stderr)
            return 2
    else:
        try:
            print(payload, end="")
        except BrokenPipeError:
            return 0
    print(f"endpoints={len(contract['endpoints'])}", file=sys.stderr)
    return 0


def _cmd_diff(args) -> int:
    base_src = args.base or args.base_dir
    head_src = args.head or args.head_dir
    if not base_src or not head_src:
        print("breakproof diff: need --base/--base-dir and --head/--head-dir",
              file=sys.stderr)
        return 2
    try:
        base = _load_contract(base_src)
        head = _load_contract(head_src)
    except ValueError as exc:
        print(f"breakproof: {exc}", file=sys.stderr)
        return 2
    gate = build_gate(base, head, base_ref=args.base_ref or "",
                      head_ref=args.head_ref or "")
    md = render_gate_markdown(gate)
    try:
        if args.markdown:
            _write_file(args.markdown, md + "\n")
        else:
            print(md)
    except (OSError, BrokenPipeError) as exc:
        if isinstance(exc, BrokenPipeError):
            return 0
        print(f"breakproof: cannot write {args.markdown}: {exc}", file=sys.stderr)
        return 2
    if args.out_gate:
        try:
            _write_file(args.out_gate,
                        json.dumps(gate, indent=2, sort_keys=True) + "\n")
        except OSError as exc:
            print(f"breakproof: cannot write {args.out_gate}: {exc}", file=sys.stderr)
            return 2
    if args.radar_markdown:
        try:
            _write_file(args.radar_markdown,
                        render_radar_markdown(gate.get("diff", {}),
                                              args.head_ref or "") + "\n")
        except OSError as exc:
            print(f"breakproof: cannot write {args.radar_markdown}: {exc}",
                  file=sys.stderr)
            return 2
    verdict = gate.get("verdict", "pass")
    print(f"verdict={verdict}", file=sys.stderr)
    return 1 if verdict == "fail" else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="breakproof",
        description="Fail the PR only when an API contract vanished. No spec needed.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="Read a directory, print its contracts.")
    s.add_argument("path", help="Directory to read. Only read, promise.")
    s.add_argument("--out", default="", help="Write contract JSON here, else stdout.")
    s.add_argument("--service", default="", help="Label every endpoint with this service.")
    s.set_defaults(func=_cmd_scan)

    d = sub.add_parser("diff", help="Base vs head. Removals fail, additions don't.")
    d.add_argument("--base", default="", help="Base contract JSON, or nothing.")
    d.add_argument("--head", default="", help="Head contract JSON, or nothing.")
    d.add_argument("--base-dir", default="", help="Scan this dir as base instead.")
    d.add_argument("--head-dir", default="", help="Scan this dir as head instead.")
    d.add_argument("--base-ref", default="")
    d.add_argument("--head-ref", default="")
    d.add_argument("--out-gate", default="")
    d.add_argument("--markdown", default="")
    d.add_argument("--radar-markdown", default="")
    d.set_defaults(func=_cmd_diff)
    return p


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args) or 0)
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
