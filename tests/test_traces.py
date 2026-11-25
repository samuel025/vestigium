import json, pathlib
from vestigium.generator import all_cases

ROWS = [json.loads(l) for l in pathlib.Path("results/traces.jsonl").read_text().splitlines()]
CASES = {c["id"]: c for c in all_cases()}


def test_traces_are_real_transcripts():
    assert len(ROWS) >= 20
    for r in ROWS:
        assert r["label"] == CASES[r["case"]]["label"]
        stored = {p["id"] for l, p in CASES[r["case"]]["nodes"] if l == "Passage"} | {d["id"] for d in CASES[r["case"]]["distractors"]}
        for c in r["citations"]:
            assert c["valid"] == (c["id"] in stored)                      # the citation check in the UI is the real one
        if r["arm"] == "C":
            assert any(s["tool"] == "run_all_checks" for s in r["trace"])  # the rule engine was actually consulted
            assert r["tool_calls"] == len(r["trace"])
        else:
            assert r["trace"] == []                                         # documents-only arm has no tools
