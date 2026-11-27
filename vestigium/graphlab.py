"""The graph lab: show Relate working. Read-only Cypher against a throwaway copy of a case graph, preset
walkthrough queries, and 'remove one relationship' experiments (what does the engine say when a link is missing?).
Nothing here can change a stored graph: every call builds a fresh in-memory copy."""
import re
from .engine import run_checks, PACKS
from .whatif import build

REMOVABLE = ("FOLLOWS", "ACTED_UNDER", "CLEARED_BY", "GRANTED_BY", "REVOKED_BY")      # the relationships whose absence the rules can notice

PRESETS = {
    "chain": dict(title="Walk the chain", text="Each transfer, who sold, who bought, and the earlier transfer it follows", cypher="""
MATCH (t:Transfer)-[:MOVES]->(:Asset {id:$asset}), (g:Party)-[:FROM]->(t), (t)-[:TO]->(h:Party)
OPTIONAL MATCH (t)-[:FOLLOWS]->(p:Transfer)
RETURN t.id AS transfer, t.effective AS effective, g.name AS seller, h.name AS buyer, p.id AS follows
ORDER BY t.effective, t.id"""),
    "depends": dict(title="What rests on each sale", text="For every sale, how many later sales follow from it (if it is broken, all of them are affected)", cypher="""
MATCH (t:Transfer)-[:MOVES]->(:Asset {id:$asset})
OPTIONAL MATCH (later:Transfer)-[:FOLLOWS*1..60]->(t)
RETURN t.id AS transfer, t.effective AS signed, count(DISTINCT later) AS later_sales_resting_on_it
ORDER BY t.effective, t.id"""),
    "authority": dict(title="Who signed under what authority", text="Agent-signed transfers and the authority they cite", cypher="""
MATCH (t:Transfer)-[:ACTED_UNDER]->(au:Authority)
RETURN t.id AS transfer, t.effective AS signed, au.agent AS agent, au.valid_from AS valid_from, au.valid_to AS valid_to,
       t.effective >= au.valid_from AND (au.valid_to IS NULL OR t.effective <= au.valid_to) AS in_window
ORDER BY t.effective"""),
}

_WRITE = re.compile(r"\b(create|merge|delete|detach|set|remove|drop|call|load|foreach|index|constraint)\b", re.I)
_STR = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")


def rules_info(pack):
    return [dict(id=k, kind=v["kind"], text=v["text"], cypher=v["cypher"].strip()) for k, v in PACKS[pack].items()]


def check_read_only(q):
    """Return an error string, or None when the query is a read-only statement."""
    if not q or not q.strip(): return "Type a query first."
    if len(q) > 2000: return "Query too long (max 2000 characters)."
    bare = _STR.sub("''", re.sub(r"//[^\n]*", "", q))
    if ";" in bare.strip().rstrip(";"): return "One statement at a time."
    m = _WRITE.search(bare)
    if m: return f"This console is read-only: '{m.group(0).upper()}' is not allowed."
    if not re.search(r"\b(match|return|with|unwind)\b", bare, re.I): return "Start with MATCH … RETURN …"
    return None


def _clean(v):
    if hasattr(v, "labels"):                                   # a Relate node: show its labels and properties
        try: return {"_node": list(v.labels), **{k: str(x) for k, x in dict(v.properties).items()}}
        except Exception: return str(v)
    if isinstance(v, (list, tuple)): return [_clean(x) for x in v]
    if isinstance(v, dict): return {k: _clean(x) for k, x in v.items()}
    if v is None or isinstance(v, (bool, int, float, str)): return v
    return str(v)


def case_params(case):
    return {"asset": case["asset"], "as_of": case["as_of"], "known": case["as_of"]}


def run_cypher(case, query, limit=100):
    """Run a read-only query on a fresh copy of the case graph. Returns {columns, rows, truncated} or {error}."""
    err = check_read_only(query)
    if err: return {"error": err}
    db = build(case)
    try: rows = db.execute(query, case_params(case)).data()
    except Exception as e: return {"error": "Relate could not run that: " + str(e).splitlines()[0][:160]}
    cols = list(rows[0].keys()) if rows else []
    return {"columns": cols, "rows": [{k: _clean(v) for k, v in r.items()} for r in rows[:limit]], "truncated": len(rows) > limit, "total": len(rows)}


def without(case, edge):
    """A copy of the case with one relationship removed. edge = [from, type, to]."""
    e = tuple(edge)
    return {**case, "rels": [r for r in case["rels"] if tuple(r) != e]}


def _sig(res):
    return {f"{x['rule']}@{x['transfer']}": x for x in res["findings"] + res["missing"]}


def remove_edge(case, edge, base=None):
    """What does the engine say with this one relationship gone? Returns the new verdict and what changed."""
    base = base or run_checks(build(case), case["asset"], case["as_of"], pack=case["pack"])
    if tuple(edge) not in {tuple(r) for r in case["rels"]}: return {"error": "No such relationship."}
    res = run_checks(build(without(case, edge)), case["asset"], case["as_of"], pack=case["pack"])
    b, a = _sig(base), _sig(res)
    return dict(edge=list(edge), verdict=res["verdict"], before=base["verdict"],
                new=[dict(key=k, rule=a[k]["rule"], transfer=a[k]["transfer"], detail=a[k]["detail"], evidence=a[k].get("evidence", []), missing=a[k].get("missing"), kind="gap" if a[k] in res["missing"] else "defect") for k in a if k not in b],
                gone=[k for k in b if k not in a])


def experiments(case):
    """Every removable relationship of a case -> its outcome (precomputed for the static demo)."""
    base = run_checks(build(case), case["asset"], case["as_of"], pack=case["pack"])
    out = {}
    for r in case["rels"]:
        if r[1] in REMOVABLE:
            o = remove_edge(case, r, base)
            out[">".join(r)] = dict(v=o["verdict"], new=o["new"], gone=o["gone"])
    return out


def preset_rows(case):
    out = {}
    for k, p in PRESETS.items():
        r = run_cypher(case, p["cypher"])
        out[k] = r if "error" not in r else dict(columns=[], rows=[])
    return out


def case_from_client(body, known):
    """A case from the request: a built-in id, or the graph of a pasted dossier the browser sends back."""
    if body.get("case") in known: return known[body["case"]]
    nodes, rels = body.get("nodes"), body.get("rels")
    if not (isinstance(nodes, list) and isinstance(rels, list)) or len(nodes) > 400 or len(rels) > 1500: return None
    asset = next((n["id"] for n in nodes if n.get("label") == "Asset"), None)
    pack = body.get("pack") if body.get("pack") in PACKS else "property"
    if not asset or not isinstance(body.get("as_of"), str): return None
    return dict(nodes=[(n["label"], {k: v for k, v in n.items() if k != "label"}) for n in nodes], rels=[tuple(r) for r in rels],
                asset=asset, as_of=body["as_of"], pack=pack)
