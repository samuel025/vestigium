from vestigium.engine import open_graph, load_case, run_checks

def base(extra_nodes=(), extra_rels=(), t2_by="Bob", t2_date="2024-03-01"):
    nodes = [
        ("Asset", dict(id="A1")),
        ("Party", dict(id="alice", name="Alice")), ("Party", dict(id="bob", name="Bob")), ("Party", dict(id="carol", name="Carol")),
        ("Transfer", dict(id="T1", effective="2022-01-01", recorded="2022-01-05", root=True)),
        ("Transfer", dict(id="T2", effective=t2_date, recorded="2024-03-02")),
        ("Passage", dict(id="P1", text="Alice conveys to Bob")), ("Passage", dict(id="P2", text="Bob conveys to Carol")),
    ] + list(extra_nodes)
    rels = [("T1","MOVES","A1"),("T2","MOVES","A1"),("T1","TO","bob"),("T2","TO","carol"),
            ("alice","FROM","T1"),("bob" if t2_by=="Bob" else "alice","FROM","T2"),
            ("T2","FOLLOWS","T1"),("T1","EVIDENCED_BY","P1"),("T2","EVIDENCED_BY","P2")] + list(extra_rels)
    return dict(nodes=nodes, rels=rels)

def run(case, **kw):
    db = open_graph(); load_case(db, case)
    return run_checks(db, "A1", kw.get("as_of", "2025-06-01"))

def test_clean():
    assert run(base())["verdict"] == "clean"

def test_chain_break():
    r = run(base(t2_by="Alice"))
    assert r["verdict"] == "defective" and r["findings"][0]["rule"] == "PROP-CHAIN"

def test_date():
    assert any(f["rule"] == "PROP-DATE" for f in run(base(t2_date="2021-01-01"))["findings"])

def test_expired_authority():
    case = base(extra_nodes=[("Authority", dict(id="AU1", agent="Dan", valid_from="2023-01-01", valid_to="2024-01-01"))],
                extra_rels=[("T2","ACTED_UNDER","AU1")])
    case["nodes"] = [(l, {**p, "by_agent": True} if p.get("id")=="T2" else p) for l, p in case["nodes"]]
    assert any(f["rule"] == "PROP-AUTH" for f in run(case)["findings"])

def test_missing_authority_is_inconclusive():
    case = base()
    case["nodes"] = [(l, {**p, "by_agent": True} if p.get("id")=="T2" else p) for l, p in case["nodes"]]
    r = run(case); assert r["verdict"] == "inconclusive" and r["missing"][0]["rule"] == "PROP-AUTH-MISSING"

def test_known_as_of_replay():
    case = base(t2_by="Alice")
    db = open_graph(); load_case(db, case)
    assert run_checks(db, "A1", "2025-06-01", known="2024-02-01")["verdict"] == "clean"  # T2 not yet recorded
