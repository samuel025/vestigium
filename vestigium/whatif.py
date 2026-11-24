from .engine import open_graph, load_case, run_checks


def build(case, extra=None):
    db = open_graph()
    load_case(db, dict(nodes=case["nodes"] + (extra or {}).get("nodes", []), rels=case["rels"] + (extra or {}).get("rels", [])))
    for nid, prop, val in (extra or {}).get("set", []):
        db.execute(f"MATCH (n {{id:$i}}) SET n.{prop} = $v", {"i": nid, "v": val})
    return db


def would_fix(case, fix, as_of=None, pack=None):
    """Rehearse a hypothetical record on a throwaway copy; True if the verdict turns clean."""
    db = build(case, fix)
    return run_checks(db, case["asset"], as_of or case["as_of"], pack=pack or case.get("pack", "property"))
