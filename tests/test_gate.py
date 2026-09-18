import pathlib

from breakproof.extract import extract_endpoints_from_text, scan_path
from breakproof.prgate import build_gate
from breakproof.radar import break_key, build_api_diff, normalize_path


def _contract(*eps):
    return {"endpoints": [{"method": m, "path": p, "protocol": "http",
                           "service": "api", "handler": "", "file": "a.py", "line": 1}
                          for m, p in eps], "edges": []}


def test_break_key_stable():
    assert break_key("get", "/users/") == "API-GET-/users"
    assert break_key("POST", "orders") == "API-POST-/orders"
    assert normalize_path("") == "/"


def test_diff_removed_and_added():
    prev = _contract(("GET", "/users"), ("DELETE", "/gone"))
    curr = _contract(("GET", "/users"), ("GET", "/new"))
    diff = build_api_diff(prev, curr)
    assert diff["summary"]["breaking"] == 1
    assert [r["path"] for r in diff["removed"]] == ["/gone"]
    assert [r["path"] for r in diff["added"]] == ["/new"]


def test_diff_deterministic_and_additions_never_break():
    prev = _contract(("GET", "/users"),)
    curr = _contract(("GET", "/users"), ("POST", "/users"))
    again = build_api_diff(prev, curr)
    assert build_api_diff(prev, curr) == again
    assert again["summary"]["breaking"] == 0


def test_gate_pass_and_fail():
    base = _contract(("GET", "/users"),)
    assert build_gate(base, base)["verdict"] == "pass"
    head = _contract(("GET", "/users"), ("GET", "/new"))
    assert build_gate(base, head)["verdict"] == "pass"
    removed = _contract()
    gate = build_gate(base, removed, base_ref="main", head_ref="pr")
    assert gate["verdict"] == "fail"
    assert gate["summary"]["breaking"] == 1


def test_gate_new_cves_and_secrets_fail():
    base = _contract(("GET", "/users"),)
    gate = build_gate(base, base, head_affected={"CVE-2024-0001"})
    assert gate["verdict"] == "fail"
    gate2 = build_gate(base, base, head_secrets={("a.py", "2")})
    assert gate2["verdict"] == "fail"


def test_extract_python_and_js():
    py = '@app.get("/users")\ndef f(): pass\n'
    assert ("GET", "/users", 1) in extract_endpoints_from_text(py, "py")
    js = 'app.post("/orders", h)\n'
    assert ("POST", "/orders", 1) in extract_endpoints_from_text(js, "js")


def test_scan_path_sorts():
    import os
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="breakproof-test-")
    try:
        with open(os.path.join(tmp, "b.py"), "w", encoding="utf-8") as fh:
            fh.write('@app.delete("/z")\ndef a(): pass\n')
        with open(os.path.join(tmp, "a.py"), "w", encoding="utf-8") as fh:
            fh.write('@app.get("/a")\ndef b(): pass\n')
        contract = scan_path(tmp)
        assert [(e["method"], e["path"]) for e in contract["endpoints"]] == [
            ("DELETE", "/z"), ("GET", "/a")]
        assert {e["service"] for e in contract["endpoints"]} == {"app"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def test_extract_ignores_garbage():
    assert extract_endpoints_from_text("", "py") == []
    assert extract_endpoints_from_text(None, "py") == []
    assert extract_endpoints_from_text("hello", "cobol") == []
    assert extract_endpoints_from_text("@app.get(123)", "py") == []


def test_scan_rejects_nonsense():
    import pytest
    with pytest.raises(ValueError):
        scan_path("")
    with pytest.raises(ValueError):
        scan_path("/definitely/not/a/real/dir/breakproof")


def test_package_is_read_only():
    src = (pathlib.Path(__file__).resolve().parent.parent / "breakproof").glob("*.py")
    banned = ("os.remove", "os.unlink", "os.rmdir", "shutil.rmtree", "os.system",
              "subprocess", "eval(", "exec(")
    for path in src:
        text = path.read_text(encoding="utf-8")
        assert not any(b in text for b in banned), path.name


def test_cli_roundtrip():
    import json
    import os
    import shutil
    import tempfile
    from breakproof.cli import main
    tmp = tempfile.mkdtemp(prefix="breakproof-cli-")
    try:
        with open(os.path.join(tmp, "a.py"), "w", encoding="utf-8") as fh:
            fh.write('@app.get("/a")\ndef f(): pass\n')
        assert main(["scan", tmp, "--out", os.path.join(tmp, "c.json")]) == 0
        with open(os.path.join(tmp, "c.json"), encoding="utf-8") as fh:
            assert len(json.load(fh)["endpoints"]) == 1
        assert main(["diff", "--base", os.path.join(tmp, "c.json"),
                     "--head", os.path.join(tmp, "c.json")]) == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_examples_cover_three_languages():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent / "examples"
    contract = scan_path(str(root))
    by_service = {}
    for e in contract["endpoints"]:
        by_service.setdefault(e["service"], []).append((e["method"], e["path"]))
    assert set(by_service) == {"python-api", "express-api", "go-api"}
    assert len(contract["endpoints"]) == 8
