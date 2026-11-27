import relate
from .rules import PROPERTY_RULES, VEHICLE_RULES

PACKS = {"property": PROPERTY_RULES, "vehicle": VEHICLE_RULES}


def open_graph(path=":memory:"):
    return relate.connect(path)


def load_case(db, case):
    """case: {nodes:[(label, props)], rels:[(from_id, type, to_id)]} with ISO date strings."""
    DATES = {"effective", "recorded", "valid_from", "valid_to", "died", "died_recorded"}
    for label, props in case["nodes"]:
        sets = ", ".join(f"{k}: date(${k})" if k in DATES and v else f"{k}: ${k}" for k, v in props.items())
        db.execute(f"CREATE (:{label} {{{sets}}})", props)
    for a, typ, b in case["rels"]:
        db.execute(f"MATCH (a {{id:$a}}), (b {{id:$b}}) CREATE (a)-[:{typ}]->(b)", {"a": a, "b": b})


def run_checks(db, asset, as_of, known=None, pack="property"):
    """Deterministic verdict. Returns {verdict, findings, missing}."""
    params = {"asset": asset, "as_of": as_of, "known": known or as_of}
    findings, missing = [], []
    for rule_id, rule in PACKS[pack].items():
        for row in db.execute(rule["cypher"], params).data():
            f = {"rule": rule_id, "text": rule["text"], "fix_type": rule.get("fix_type"), **row}
            (missing if rule["kind"] == "gap" else findings).append(f)
    order = lambda f: (len(f["transfer"]), f["transfer"], f["rule"])   # deterministic: chain order, then rule
    if not db.execute("MATCH (:Transfer)-[:MOVES]->(:Asset {id:$asset}) RETURN count(*) AS n", params).data()[0]["n"]:
        # nothing to check is not "clean": say what is missing instead of vouching for an empty chain
        missing.append({"rule": "NO-RECORDS", "text": "No ownership records could be read", "fix_type": "provide_records", "transfer": "-",
                        "detail": "No transfer of this asset was found, so no check could run", "missing": "the deeds or titles for this asset", "evidence": []})
    findings.sort(key=order); missing.sort(key=order)
    verdict = "defective" if findings else "inconclusive" if missing else "clean"
    return {"verdict": verdict, "findings": findings, "missing": missing, "downstream": downstream(db, params, findings + missing)}


# Every later sale that rests on a broken one: walk FOLLOWS backwards from each later transfer to the flagged one.
DOWNSTREAM = """
MATCH (later:Transfer)-[:FOLLOWS*1..60]->(t:Transfer {id:$t}), (later)-[:MOVES]->(:Asset {id:$asset})
WHERE later.effective <= date($as_of) AND later.recorded <= date($known)
RETURN DISTINCT later.id AS transfer"""


def downstream(db, params, flagged):
    """Later sales that depend on a flagged one, and which flagged sale(s) they depend on. A sale that is itself
    flagged is reported as a finding, not here, so the three groups (broken, affected, fine) never overlap."""
    own = {f["transfer"] for f in flagged}
    dep = {}
    for t in sorted(own - {"-"}):
        for row in db.execute(DOWNSTREAM, {**params, "t": t}).data():
            if row["transfer"] not in own:
                dep.setdefault(row["transfer"], set()).add(t)
    key = lambda x: (len(x), x)
    return [dict(transfer=t, depends_on=sorted(r, key=key)) for t, r in sorted(dep.items(), key=lambda kv: key(kv[0]))]


def timeline(db, asset, dates, as_of):
    """Verdict across known-as-of dates (valid-as-of fixed): e.g. clean until a late-recorded deed arrives."""
    return [(d, run_checks(db, asset, as_of, known=d)["verdict"]) for d in dates]


CODE = {"clean": 0, "defective": 1, "inconclusive": 2}


def two_times(db, case, pack=None):
    """The verdict for every pair of dates: legally true on V (which sales had been signed) x known on K (which deeds had
    reached the register). V runs over the signing dates, K over the signing and recording dates (so 'signed, not yet filed' is always visible), both ending at the case's as-of date.
    Returns vdates, kdates and grid[v][k] = [verdict code, "RULE@T,..."] (compact, for the static demo)."""
    pack = pack or case.get("pack", "property")
    tr = [p for l, p in case["nodes"] if l == "Transfer"]
    vdates = sorted({p["effective"] for p in tr if p.get("effective") and p["effective"] <= case["as_of"]} | {case["as_of"]})
    kdates = sorted({p[k] for p in tr for k in ("recorded", "effective") if p.get(k) and p[k] <= case["as_of"]} | {case["as_of"]})
    grid = []
    for v in vdates:
        row = []
        for k in kdates:
            r = run_checks(db, case["asset"], v, known=k, pack=pack)
            row.append([CODE[r["verdict"]], ",".join(f"{f['rule']}@{f['transfer']}" for f in r["findings"] + r["missing"])])
        grid.append(row)
    return dict(vdates=vdates, kdates=kdates, grid=grid)
