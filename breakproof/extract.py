"""Find HTTP routes in a directory. Read-only; wouldn't delete your files if you paid it.

Covers common Flask/FastAPI/Express/Go patterns. Anything exotic is reported
as nothing rather than guessed at — a missed route is an honest gap, a fake
route is a lie.
"""

from __future__ import annotations

import bisect
import os
import re

MAX_FILE_BYTES = 1_000_000
MAX_FILES = 50_000
MAX_ENDPOINTS = 20_000
MAX_PATH_LEN = 2048

SCAN_EXTS = (".py", ".js", ".jsx", ".ts", ".tsx", ".go")
SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", ".idea", "node_modules", "dist", "build", "__pycache__",
    ".venv", "venv", ".tox", "vendor",
})

_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")

_PY_DECORATOR = re.compile(
    r"""@(?:[\w.]+\.)?(get|post|put|delete|patch|head|options)\s*\(\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_PY_ROUTE = re.compile(
    r"""@(?:[\w.]+\.)?route\s*\(\s*["']([^"']+)["']\s*(?:,\s*methods\s*=\s*\[([^\]]{0,512})\])?""",
    re.IGNORECASE,
)
_PY_METHOD = re.compile(r"""["'](\w{3,7})["']""")
_JS_ROUTE = re.compile(
    r"""(?:app|router|server|api)\s*\.\s*(get|post|put|delete|patch|head|options)\s*\(\s*["'`]([^"'`]+)["'`]""",
    re.IGNORECASE,
)
_GO_HANDLE = re.compile(r"""HandleFunc\s*\(\s*["']([^"']+)["']""")
_GO_GIN = re.compile(
    r"""\.\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(\s*["']([^"']+)["']""",
)


def _service_for(relpath: str) -> str:
    rel = (relpath or "").replace("\\", "/")
    if "/" not in rel:
        return "app"
    return rel.split("/", 1)[0] or "app"


def _line_offsets(text: str) -> list:
    offsets, total = [0], 0
    for line in text.splitlines(keepends=True):
        total += len(line)
        offsets.append(total)
    return offsets


def _line_of(offsets: list, pos: int) -> int:
    return bisect.bisect_right(offsets, pos)


def _valid_route(path: str) -> bool:
    return bool(path) and path.startswith("/") and len(path) <= MAX_PATH_LEN and " " not in path


def extract_endpoints_from_text(text, lang: str) -> list:
    """Pull (method, path, line) triples out of one file's text."""
    if not isinstance(text, str) or not text or not isinstance(lang, str):
        return []
    offsets = _line_offsets(text)
    found = []

    def line_at(pos: int) -> int:
        return _line_of(offsets, pos)

    if lang == "py":
        for m in _PY_DECORATOR.finditer(text):
            if _valid_route(m.group(2)):
                found.append((m.group(1).upper(), m.group(2), line_at(m.start())))
        for m in _PY_ROUTE.finditer(text):
            if not _valid_route(m.group(1)):
                continue
            methods = _PY_METHOD.findall(m.group(2) or "GET")
            methods = [x.upper() for x in methods if x.upper() in _METHODS] or ["GET"]
            for meth in methods:
                found.append((meth, m.group(1), line_at(m.start())))
    elif lang in ("js", "ts"):
        for m in _JS_ROUTE.finditer(text):
            if _valid_route(m.group(2)):
                found.append((m.group(1).upper(), m.group(2), line_at(m.start())))
    elif lang == "go":
        for m in _GO_HANDLE.finditer(text):
            if _valid_route(m.group(1)):
                found.append(("GET", m.group(1), line_at(m.start())))
        for m in _GO_GIN.finditer(text):
            if _valid_route(m.group(2)):
                found.append((m.group(1).upper(), m.group(2), line_at(m.start())))
    return found


def _lang_of(filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".py":
        return "py"
    if ext == ".go":
        return "go"
    if ext in (".js", ".jsx"):
        return "js"
    return "ts"


def _iter_files(root: str) -> list:
    """Collect candidate files. Skips symlinks — cute trick, not today."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
            and not os.path.islink(os.path.join(dirpath, d))
        )
        for fn in sorted(filenames):
            if not fn.endswith(SCAN_EXTS):
                continue
            full = os.path.join(dirpath, fn)
            if os.path.islink(full):
                continue
            out.append(full)
            if len(out) >= MAX_FILES:
                return out
    return out


def scan_path(root: str, service: str = "") -> dict:
    """Scan a directory into a contract. Never writes, never deletes, never executes."""
    if not isinstance(root, str) or not root:
        raise ValueError("scan root must be a non-empty path")
    if not os.path.isdir(root):
        raise ValueError(f"not a directory: {root}")
    endpoints, seen = [], set()
    for path in _iter_files(root):
        try:
            if os.path.getsize(path) > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except (OSError, ValueError):
            continue
        try:
            rel = os.path.relpath(path, root).replace("\\", "/")
        except ValueError:
            continue
        if rel.startswith(".."):
            continue
        svc = service or _service_for(rel)
        for method, route, line in extract_endpoints_from_text(text, _lang_of(path)):
            key = (method, route, rel, line)
            if key in seen:
                continue
            seen.add(key)
            endpoints.append({"method": method, "path": route, "protocol": "http",
                              "service": svc, "handler": "", "file": rel, "line": line})
            if len(endpoints) >= MAX_ENDPOINTS:
                break
        if len(endpoints) >= MAX_ENDPOINTS:
            break
    endpoints.sort(key=lambda e: (e["method"], e["path"], e["file"], str(e["line"])))
    return {"endpoints": endpoints, "edges": []}
