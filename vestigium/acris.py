"""Real records: NYC ACRIS deeds (public records via NYC Open Data) -> Vestigium graphs -> the same rule engine.

    uv run python -m vestigium.acris          # needs data/acris_raw/{legals,master,parties}.json (see README)

What this is and is not:
- ACRIS gives each recorded deed a document date, a recorded date, and its party-1 (grantor) and party-2 (grantee) names.
  It does NOT say which earlier deed a seller acquired through, so the importer links deeds in recorded order (FOLLOWS)
  and treats the earliest deed in the window as the start of the chain. The rules then check every link.
- Names are messy ("DOE, JANE" vs "ESTATE OF JANE DOE" vs "JANE DOE REVOCABLE TRUST"). The importer, not the
  engine, decides whether a seller is the previous buyer, using a stated, deliberately simple name match (`same`).
  Every mismatch is listed so a person can judge it.
- Raw downloads contain real people's names and stay in data/acris_raw/ (gitignored). The committed report is anonymised.
- Mortgages and satisfactions are not checked: ACRIS does not link a satisfaction to its mortgage in the fields we fetched,
  and in New York a mortgage is normally paid off at closing with the satisfaction recorded weeks later, so the synthetic
  lien rule would mislabel ordinary sales.
"""
import json, pathlib, re
from collections import Counter, defaultdict
from .engine import run_checks
from .whatif import build

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "acris_raw"

ROLE = re.compile(r"\b(THE ESTATE OF|ESTATE OF|ESTATE|AS EXECUTOR|AS EXECUTRIX|EXECUTOR|EXECUTRIX|AS ADMINISTRATOR(?: C\.?T\.?A)?|ADMINISTRATOR|ADMINISTRATTRIX|"
                  r"SUCCESSOR TRUSTEE|AS TRUSTEE|TRUSTEE|DECEASED|AS SOLE HEIR AT LAW|HUSBAND AND WIFE|REVOCABLE TRUST|IRREVOCABLE TRUST|IRREV TRUST|"
                  r"LIVING TRUST|FAMILY TRUST|DECLARATION OF TRUST|TRUST|U/W/O|U/A|A/K/A|JR)\b\.?")
SUFFIX = {"LLC", "INC", "CORP", "CO", "THE", "AND", "OF"}


def tokens(name):
    s = ROLE.sub(" ", str(name).upper())
    return {t for t in re.split(r"[^A-Z0-9]+", s) if len(t) > 1 and not t.isdigit() and t not in SUFFIX}


def same(a, b):
    """Two names are the same party if their tokens are equal, or one contains the other and they share at least two
    tokens (first name + surname; tolerates middle initials, 'AS TRUSTEE', 'ESTATE OF', a person's own trust)."""
    A, B = tokens(a), tokens(b)
    if not A or not B: return False
    return A == B or (len(A & B) >= 2 and (A <= B or B <= A))


def group_match(sellers, buyers):
    return any(same(s, b) for s in sellers for b in buyers)


def load():
    legals = json.loads((RAW / "legals.json").read_text())
    master = json.loads((RAW / "master.json").read_text())
    parties = json.loads((RAW / "parties.json").read_text())
    who = defaultdict(lambda: {"1": set(), "2": set()})
    for p in parties:
        who[p["document_id"]][p["party_type"]].add(p["name"])
    lots = defaultdict(set)
    for r in legals:
        lots[(r["borough"], r["block"], r["lot"])].add(r["document_id"])
    return lots, master, who


def _d(s):
    return (s or "")[:10] or None


def chains(lots, master, who):
    """Per lot: its deeds in recorded order, with both dates and both party groups."""
    out = []
    for lot, ids in sorted(lots.items()):
        deeds = [master[i] for i in ids if i in master and master[i]["doc_type"] in ("DEED", "DEEDO") and i in who]
        deeds = [d for d in deeds if who[d["document_id"]]["1"] and who[d["document_id"]]["2"]]
        if len(deeds) < 2: continue
        deeds.sort(key=lambda d: (_d(d["recorded_datetime"]), _d(d.get("document_date")) or "", d["document_id"]))
        out.append((lot, [dict(id=d["document_id"], effective=_d(d.get("document_date")) or _d(d["recorded_datetime"]),
                               recorded=_d(d["recorded_datetime"]), amount=float(d.get("document_amt") or 0),
                               sellers=sorted(who[d["document_id"]]["1"]), buyers=sorted(who[d["document_id"]]["2"])) for d in deeds]))
    return out


def to_case(k, deeds):
    """One lot -> a Vestigium case. The seller is the SAME party node as the previous buyer only if the names match."""
    nodes = [("Asset", dict(id="A1", address=f"Brooklyn lot {k} (anonymised)"))]
    rels, owner = [], None
    for i, d in enumerate(deeds, 1):
        t = f"T{i}"
        props = dict(id=t, effective=d["effective"], recorded=d["recorded"])
        if i == 1: props["root"] = True
        nodes.append(("Transfer", props))
        if owner and group_match(d["sellers"], deeds[i - 2]["buyers"]):
            seller = owner
        else:
            seller = f"S{i}"; nodes.append(("Party", dict(id=seller, name=f"seller group {i}")))
        buyer = f"B{i}"; nodes.append(("Party", dict(id=buyer, name=f"buyer group {i}")))
        pid = f"P{i}"
        nodes.append(("Passage", dict(id=pid, doc=f"deed-{i}", text=f"DEED dated {d['effective']}, recorded {d['recorded']}: "
                                      f"{len(d['sellers'])} grantor name(s) convey to {len(d['buyers'])} grantee name(s).")))
        rels += [(t, "MOVES", "A1"), (seller, "FROM", t), (t, "TO", buyer), (t, "EVIDENCED_BY", pid)]
        if i > 1: rels.append((t, "FOLLOWS", f"T{i-1}"))
        owner = buyer
    as_of = max(d["recorded"] for d in deeds)
    return dict(id=f"real-{k}", nodes=nodes, rels=rels, asset="A1", as_of=as_of, pack="property")


def run():
    lots, master, who = load()
    rows, review = [], []
    for k, (lot, deeds) in enumerate(chains(lots, master, who), 1):
        case = to_case(k, deeds)
        res = run_checks(build(case), "A1", case["as_of"], pack="property")
        found = [dict(rule=f["rule"], transfer=f["transfer"]) for f in res["findings"] + res["missing"]]
        rows.append(dict(lot=k, deeds=len(deeds), verdict=res["verdict"], findings=found, _deeds=[dict(effective=d["effective"], recorded=d["recorded"]) for d in deeds],
                         gap_days=[(_days(d["effective"], d["recorded"])) for d in deeds]))
        for f in res["findings"]:
            i = int(f["transfer"][1:])
            review.append(dict(lot=k, rule=f["rule"], transfer=f["transfer"], deed=deeds[i - 1], previous=deeds[i - 2] if i > 1 else None))
    return rows, review


def _days(a, b):
    from datetime import date
    try: return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except Exception: return None


# Hand review of every finding (by a person reading the real names in data/acris_raw/review.json). Lot numbers are the
# importer's own deterministic numbering, so the committed report carries no names or addresses.
REVIEWED = {
    (7, "T2"): "false alarm: the same couple, their two-word surname written with a space when they bought and without one when they sold",
    (8, "T2"): "register inconsistency: the buyer is recorded as an exchange titleholder '...2006-175' and sells as '...2007-175'; "
               "probably the same entity, but the public record does not say so, so a person should check",
}


def report(rows, review, links):
    from statistics import median
    gaps = [g for r in rows for g in r["gap_days"] if g is not None]
    out = dict(source="NYC ACRIS via NYC Open Data (Real Property Legals 8h5j-fqxa, Master bnx9-e6tj, Parties 636b-3b5g)",
               sample="5 adjacent blocks in one Brooklyn neighbourhood, deeds recorded 2003-2026",
               lots=len(rows), deeds=sum(r["deeds"] for r in rows), links=sum(links.values()), link_match=dict(links),
               verdicts=dict(Counter(r["verdict"] for r in rows)),
               findings=[dict(lot=f["lot"], rule=f["rule"], transfer=f["transfer"], review=REVIEWED.get((f["lot"], f["transfer"]), "not reviewed"))
                         for f in review],
               days_signing_to_recording=dict(median=median(gaps), max=max(gaps), over_90=sum(g > 90 for g in gaps), of=len(gaps)),
               signed_before_previous_recorded=sum(1 for r in rows for a, b in zip(r["_deeds"], r["_deeds"][1:]) if b["effective"] < a["recorded"]),
               per_lot=[dict(lot=r["lot"], deeds=r["deeds"], verdict=r["verdict"], findings=r["findings"]) for r in rows])
    return out


def export_app(path=ROOT / "demo" / "real.js"):
    """Every real lot as an app case (anonymised: owners are numbered, no names, no addresses), with the same
    verdict, timeline, proof and graph-lab data as the synthetic cases. Needs the raw downloads; the output is committed."""
    from .proof import proofs
    from .graphlab import experiments, preset_rows
    lots, master, who = load()
    out = []
    for k, (lot, deeds) in enumerate(chains(lots, master, who), 1):
        case = to_case(k, deeds)
        owner, names = 1, {}
        for l, p in case["nodes"]:                       # readable anonymous names: Owner 1 sold to Owner 2, ...
            if l == "Party":
                if p["id"].startswith("B"): owner += 1; names[p["id"]] = f"Owner {owner}"
                else: names[p["id"]] = f"Owner {owner}" if p["id"] == "S1" else f"Unmatched seller at T{p['id'][1:]}"
        for l, p in case["nodes"]:
            if l == "Party": p["name"] = names[p["id"]]
        by = {(tt, a if tt == "TO" else b): (b if tt == "TO" else a) for a, tt, b in case["rels"] if tt in ("FROM", "TO")}
        for l, p in case["nodes"]:
            if l == "Passage":
                i = p["id"][1:]; d = deeds[int(i) - 1]
                p["text"] = (f"DEED dated {d['effective']}, recorded {d['recorded']}: {names[by[('FROM', 'T' + i)]]} "
                             f"({len(d['sellers'])} grantor name{'s' if len(d['sellers']) > 1 else ''} on the record) conveys to "
                             f"{names[by[('TO', 'T' + i)]]} ({len(d['buyers'])} grantee name{'s' if len(d['buyers']) > 1 else ''}).")
        r = run_checks(build(case), "A1", case["as_of"], pack="property")
        dates = sorted({d["recorded"] for d in deeds} | {case["as_of"]})
        tl = [(d, run_checks(build(case), "A1", case["as_of"], known=d, pack="property")["verdict"]) for d in dates]
        notes = [f"Reviewed by hand: {REVIEWED[(k, f['transfer'])]}." for f in r["findings"] if (k, f["transfer"]) in REVIEWED]
        notes.append("Real public record (NYC ACRIS), anonymised. The register does not say which earlier deed a seller bought through, "
                     "so deeds are linked in recorded order and names are matched by the importer.")
        out.append(dict(id=f"real-{k}", domain="property", label=None, split="real", as_of=case["as_of"],
                        kind="real-flag" if r["findings"] else "real-clean", title=f"Real lot {k}", asset="A1",
                        nodes=[dict(label=l, **p) for l, p in case["nodes"]], rels=case["rels"], result=r, timeline=tl,
                        proof=[dict(rule=x["rule"], transfer=x["transfer"], passages=x.get("passages", []), records_total=x.get("records_total", 0)) for x in proofs(case, r)],
                        fix=None, fix_verdict=None, documents="", agents={}, warnings=notes, rm=experiments(case), presets=preset_rows(case)))
    path.write_text("window.VESTIGIUM_REAL = " + json.dumps(out, default=str) + ";")
    return out


if __name__ == "__main__":
    export_app()
    rows, review = run()
    lots, master, who = load()
    links = Counter()
    for _, deeds in chains(lots, master, who):
        for a, b in zip(deeds, deeds[1:]):
            exact = any(tokens(s) and tokens(s) == tokens(x) for s in b["sellers"] for x in a["buyers"])
            links["exact" if exact else "fuzzy" if group_match(b["sellers"], a["buyers"]) else "no match"] += 1
    rep = report(rows, review, links)
    (ROOT / "results" / "acris_real.json").write_text(json.dumps(rep, indent=1))
    (RAW / "review.json").write_text(json.dumps(review, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != "per_lot"}, indent=1))
