"""Minimal proof set: the smallest group of recorded facts a finding truly rests on.

Method (delta debugging on the graph): start from every fact; try to delete chunks of facts; keep a deletion only if the
finding (same rule, same transfer) still fires. What survives cannot lose any single fact without the finding disappearing,
so it is 1-minimal: sufficient and necessary. Every other record could be deleted without changing this finding.
Deterministic and needs no LLM.
"""
from .engine import PACKS, open_graph, load_case

NODE_FACTS = {"Transfer", "Claim", "Authority", "Document", "Party"}
REL_FACTS = {"FOLLOWS", "FROM", "TO", "ACTED_UNDER", "AGAINST", "CLEARED_BY"}
DEATH = ("died", "died_recorded")


def _facts(case):
    f = [("node", p["id"]) for l, p in case["nodes"] if l in NODE_FACTS and "id" in p]
    f += [("death", p["id"]) for l, p in case["nodes"] if l == "Party" and p.get("died")]
    f += [("rel", a, t, b) for a, t, b in case["rels"] if t in REL_FACTS]
    return f


def _reduced(case, keep):
    keep = set(keep)
    drop_nodes = {p["id"] for l, p in case["nodes"] if l in NODE_FACTS and "id" in p and ("node", p["id"]) not in keep}
    nodes = []
    for l, p in case["nodes"]:
        if p.get("id") in drop_nodes: continue
        if l == "Party" and p.get("died") and ("death", p["id"]) not in keep:
            p = {k: v for k, v in p.items() if k not in DEATH}
        nodes.append((l, p))
    rels = [(a, t, b) for a, t, b in case["rels"] if a not in drop_nodes and b not in drop_nodes and (t not in REL_FACTS or ("rel", a, t, b) in keep)]
    return dict(nodes=nodes, rels=rels)


def fires(case, keep, rule, transfer, as_of=None, known=None):
    db = open_graph()
    load_case(db, _reduced(case, keep))
    params = {"asset": case["asset"], "as_of": as_of or case["as_of"], "known": known or as_of or case["as_of"]}
    return any(r["transfer"] == transfer for r in db.execute(PACKS[case["pack"]][rule]["cypher"], params).data())


def minimal_support(case, rule, transfer, as_of=None, known=None):
    facts = _facts(case)
    if not fires(case, facts, rule, transfer, as_of, known):
        return None
    keep, n = list(facts), max(len(facts) // 2, 1)
    while n >= 1:                                         # ddmin-style: drop big chunks first, then single facts
        i = 0
        while i < len(keep):
            trial = keep[:i] + keep[i + n:]
            if fires(case, trial, rule, transfer, as_of, known): keep = trial
            else: i += n
        n //= 2
    ev = {a: b for a, t, b in case["rels"] if t == "EVIDENCED_BY"}
    evid = lambda nid: sorted(b for a, t, b in case["rels"] if t == "EVIDENCED_BY" and a == nid)
    ids = [f[1] for f in keep if f[0] in ("node", "death")]
    passages = sorted({e for i in ids for e in evid(i)})
    total = sum(1 for l, p in case["nodes"] if l == "Passage") + len(case.get("distractors", []))
    return dict(rule=rule, transfer=transfer, facts=[list(f) for f in keep], passages=passages, records_total=total)


def proofs(case, result, as_of=None, known=None):
    """Minimal support for every finding and missing-record item in a result."""
    return [dict(minimal_support(case, f["rule"], f["transfer"], as_of, known) or {}, rule=f["rule"], transfer=f["transfer"])
            for f in result["findings"] + result["missing"]]
