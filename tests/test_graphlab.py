from vestigium.generator import all_cases
from vestigium.graphlab import check_read_only, run_cypher, remove_edge, experiments, case_from_client, PRESETS, without

CASES = {c["id"]: c for c in all_cases()}
CLEAN = next(c for c in CASES.values() if c["domain"] == "property" and c["label"] == "clean")


def test_writes_are_refused():
    for q in ("MATCH (n) SET n.x = 1 RETURN n", "CREATE (:A)", "MATCH (n) DETACH DELETE n", "CALL db.x()", "MATCH (n) RETURN n; MATCH (m) RETURN m"):
        assert check_read_only(q), q
    assert check_read_only("MATCH (t:Transfer) WHERE t.id = 'reset' RETURN t.id") is None     # a string literal is not a keyword


def test_presets_and_custom_query_run_on_relate():
    for p in PRESETS.values():
        r = run_cypher(CLEAN, p["cypher"])
        assert "error" not in r
    r = run_cypher(CLEAN, "MATCH (t:Transfer) RETURN count(t) AS n")
    assert r["rows"][0]["n"] == CLEAN["n_transfers"]
    assert "error" in run_cypher(CLEAN, "MATCH (n) SET n.a = 1")


def test_removing_a_follows_link_turns_clean_into_inconclusive():
    edge = next(r for r in CLEAN["rels"] if r[1] == "FOLLOWS")
    o = remove_edge(CLEAN, edge)
    assert o["before"] == "clean" and o["verdict"] == "inconclusive"
    assert any(n["rule"] == "PROP-GAP" for n in o["new"])
    assert tuple(edge) in {tuple(r) for r in CLEAN["rels"]}            # the stored case is untouched


def test_removing_authority_swaps_defect_for_missing_record():
    c = CASES["prop-014"]
    edge = next(r for r in c["rels"] if r[1] == "ACTED_UNDER")
    o = remove_edge(c, edge)
    assert o["before"] == "defective" and "PROP-AUTH@T5" in o["gone"]
    assert any(n["rule"] == "PROP-AUTH-MISSING" for n in o["new"])


def test_experiments_cover_every_removable_edge_and_pasted_graphs_work():
    ex = experiments(CASES["prop-014"])
    assert len(ex) == sum(r[1] in ("FOLLOWS", "ACTED_UNDER", "CLEARED_BY") for r in CASES["prop-014"]["rels"])
    body = dict(nodes=[dict(label=l, **p) for l, p in CLEAN["nodes"]], rels=CLEAN["rels"], as_of=CLEAN["as_of"], pack="property")
    c = case_from_client(body, CASES)
    assert c and run_cypher(c, "MATCH (n:Transfer) RETURN count(n) AS n")["rows"][0]["n"] == CLEAN["n_transfers"]
    assert case_from_client({"case": "nope"}, CASES) is None


def test_custom_queries_run_on_a_relate_read_only_copy():
    from vestigium.graphlab import query_read_only
    import pytest
    for q in ("CREATE (:Intruder)", "MATCH (n) DETACH DELETE n", "MATCH (t:Transfer) SET t.effective = date('1900-01-01') RETURN t"):
        with pytest.raises(Exception, match="ReadOnly"):
            query_read_only(CLEAN, q)                  # even with the keyword filter bypassed, Relate refuses the write
    assert query_read_only(CLEAN, "MATCH (t:Transfer) RETURN count(t) AS n")[0]["n"] == CLEAN["n_transfers"]
