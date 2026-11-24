"""Seeded synthetic benchmark generator. Produces cases with graph, documents, answer key and fix."""
import random
from datetime import date, timedelta

NAMES = ["Alder","Birch","Cedar","Dune","Elm","Fern","Gale","Heath","Iris","Juno","Knoll","Lark","Moss","Nova","Oak","Pike","Quill","Reed","Sage","Thorn"]
SURN = ["Vale","Marsh","Crane","Holt","Finch","Wren","Stone","Brook"]
iso = lambda d: d.isoformat()


def _chain(rng, n):
    names = rng.sample(NAMES, n + 2)
    parties = [dict(id=f"p{i}", name=f"{nm} {rng.choice(SURN)}") for i, nm in enumerate(names)]
    d = date(2015, 1, 1) + timedelta(days=rng.randint(0, 300))
    nodes = [("Asset", dict(id="A1", address=f"{rng.randint(1,99)} Fictional Lane, Arden"))]
    nodes += [("Party", p) for p in parties]
    rels, ts = [], []
    for i in range(1, n + 1):
        d += timedelta(days=rng.randint(120, 400))
        t = dict(id=f"T{i}", effective=iso(d), recorded=iso(d + timedelta(days=3)))
        if i == 1: t["root"] = True
        ts.append(t)
        nodes.append(("Transfer", t))
        pid = f"P{i}"
        rels += [("T%d" % i, "MOVES", "A1"), ("T%d" % i, "TO", f"p{i}"), (f"p{i-1}", "FROM", f"T{i}"), (f"T{i}", "EVIDENCED_BY", pid)]
        if i > 1: rels.append((f"T{i}", "FOLLOWS", f"T{i-1}"))
        nodes.append(("Passage", dict(id=pid, doc=f"deed-{i}", text=f"DEED dated {iso(d)}: {parties[i-1]['name']} (Grantor) conveys the property at {nodes[0][1]['address']} to {parties[i]['name']} (Grantee).")))
    return dict(nodes=nodes, rels=rels, parties=parties, ts=ts, n=n)


def _node(c, id_):
    return next(p for _, p in c["nodes"] if p.get("id") == id_)


def _set(c, id_, **kw):
    _node(c, id_).update(kw)


def _mutate(c, rng, kind, k=None):
    n = c["n"]
    k = k or rng.randint(2, n)
    key = dict(defect=None, transfer=f"T{k}", missing=None, fix=None, rule=kind)
    tk = _node(c, f"T{k}")
    if kind == "PROP-CHAIN":
        stranger = c["parties"][-1]
        c["rels"] = [(a, t, b) for a, t, b in c["rels"] if not (t == "FROM" and b == f"T{k}")] + [(stranger["id"], "FROM", f"T{k}")]
        _node(c, f"P{k}")["text"] = _node(c, f"P{k}")["text"].replace(c["parties"][k-1]["name"], stranger["name"])
    elif kind == "PROP-DUP":
        k = rng.randint(1, n - 1)
        tid = "TD"; key["transfer"] = tid
        d = date.fromisoformat(_node(c, f"T{k+1}")["effective"]) + timedelta(days=rng.randint(5, 40))
        c["nodes"] += [("Transfer", dict(id=tid, effective=iso(d), recorded=iso(d + timedelta(days=2)))),
                       ("Passage", dict(id="PD", doc="deed-dup", text=f"DEED dated {iso(d)}: {c['parties'][k]['name']} (Grantor) conveys the property to {c['parties'][-1]['name']} (Grantee)."))]
        c["rels"] += [(tid, "MOVES", "A1"), (tid, "TO", c["parties"][-1]["id"]), (f"p{k}", "FROM", tid), (tid, "FOLLOWS", f"T{k}"), (tid, "EVIDENCED_BY", "PD")]
    elif kind == "PROP-LIEN":
        k = n; key["transfer"] = f"T{n}"
        prev = date.fromisoformat(_node(c, f"T{n-1}")["effective"])
        ld = prev + timedelta(days=20)
        _lien(c, ld, rng)
        key["fix_type"] = "release_of_lien"
        key["fix"] = dict(nodes=[("Document", dict(id="REL", effective=iso(ld + timedelta(days=30)), recorded=iso(ld + timedelta(days=31)), kind="release"))],
                          rels=[("L1", "CLEARED_BY", "REL")], describe="a recorded release of the lien")
        key["missing"] = "release of lien L1"
    elif kind == "PROP-AUTH":
        d = date.fromisoformat(tk["effective"])
        tk["by_agent"] = True
        c["nodes"].append(("Authority", dict(id="AU1", agent=f"{rng.choice(NAMES)} Agent", valid_from=iso(d - timedelta(days=400)), valid_to=iso(d - timedelta(days=rng.randint(10, 120))))))
        c["nodes"].append(("Passage", dict(id="PAU", doc="poa", text="POWER OF ATTORNEY granted for a fixed term, ending before the date of this sale.")))
        c["rels"] += [(f"T{k}", "ACTED_UNDER", "AU1"), ("AU1", "EVIDENCED_BY", "PAU")]
        key["fix_type"] = "valid_authority"
        key["fix"] = dict(nodes=[("Authority", dict(id="AU2", agent="ratifier", valid_from=iso(d - timedelta(days=1)), valid_to=None))],
                          rels=[(f"T{k}", "ACTED_UNDER", "AU2")], describe="a ratifying resolution valid on the signing date")
    elif kind == "PROP-DATE":
        k = max(k, 2); key["transfer"] = f"T{k}"
        prev = date.fromisoformat(_node(c, f"T{k-1}")["effective"])
        nd = prev - timedelta(days=rng.randint(10, 60))
        _set(c, f"T{k}", effective=iso(nd), recorded=iso(prev + timedelta(days=5)))
        _node(c, f"P{k}")["text"] = _node(c, f"P{k}")["text"].replace("dated " + tk["effective"], "dated " + iso(nd))
    elif kind == "PROP-DEATH":
        gid = f"p{k-1}"; d = date.fromisoformat(tk["effective"]); dd = d - timedelta(days=rng.randint(20, 200))
        _set(c, gid, died=iso(dd), died_recorded=iso(dd + timedelta(days=10)))
        c["nodes"].append(("Passage", dict(id="PDT", doc="death-cert", text=f"CERTIFICATE OF DEATH: {_node(c, gid)['name']} died on {iso(dd)}.")))
        c["rels"].append((gid, "EVIDENCED_BY", "PDT"))
    elif kind == "PROP-GAP":
        k = max(k, 2); key["transfer"] = f"T{k}"
        c["rels"] = [(a, t, b) for a, t, b in c["rels"] if not (t == "FOLLOWS" and a == f"T{k}")]
        key["missing"] = f"record showing how {c['parties'][k-1]['name']} acquired the asset"
        key["fix_type"] = "link_previous_transfer"
        key["fix"] = dict(nodes=[], rels=[(f"T{k}", "FOLLOWS", f"T{k-1}")], describe=key["missing"])
    elif kind == "PROP-AUTH-MISSING":
        tk["by_agent"] = True
        d = date.fromisoformat(tk["effective"])
        key["missing"] = "power of attorney or resolution authorising the signatory"
        key["fix_type"] = "valid_authority"
        key["fix"] = dict(nodes=[("Authority", dict(id="AU9", agent="signatory", valid_from=iso(d - timedelta(days=30)), valid_to=None))],
                          rels=[(f"T{k}", "ACTED_UNDER", "AU9")], describe=key["missing"])
        _node(c, f"P{k}")["text"] += " Signed by an authorised agent on behalf of the Grantor."
    return key


def _lien(c, ld, rng):
    c["nodes"] += [("Claim", dict(id="L1", kind="lien", holder="Fictional Savings Bank", effective=iso(ld), recorded=iso(ld + timedelta(days=1)))),
                   ("Passage", dict(id="PL", doc="mortgage", text=f"MORTGAGE dated {iso(ld)}: the owner grants Fictional Savings Bank a lien over the property."))]
    c["rels"] += [("L1", "AGAINST", "A1"), ("L1", "EVIDENCED_BY", "PL")]


def _suspicious_clean(c, rng):
    """Looks risky but is valid: released lien, or agent with valid authority."""
    if rng.random() < .5:
        prev = date.fromisoformat(_node(c, f"T{c['n']-1}")["effective"]); ld = prev + timedelta(days=10)
        _lien(c, ld, rng)
        c["nodes"].append(("Document", dict(id="REL", effective=iso(ld + timedelta(days=20)), recorded=iso(ld + timedelta(days=21)), kind="release")))
        c["nodes"].append(("Passage", dict(id="PREL", doc="release", text="RELEASE OF MORTGAGE: the lien is fully discharged.")))
        c["rels"] += [("L1", "CLEARED_BY", "REL"), ("REL", "EVIDENCED_BY", "PREL")]
    else:
        k = rng.randint(2, c["n"]); d = date.fromisoformat(_node(c, f"T{k}")["effective"])
        _set(c, f"T{k}", by_agent=True)
        c["nodes"] += [("Authority", dict(id="AUV", agent="Valid Agent", valid_from=iso(d - timedelta(days=200)), valid_to=iso(d + timedelta(days=200)))),
                       ("Passage", dict(id="PAV", doc="poa", text="POWER OF ATTORNEY valid for two years covering this sale."))]
        c["rels"] += [(f"T{k}", "ACTED_UNDER", "AUV"), ("AUV", "EVIDENCED_BY", "PAV")]


def _distractors(c, rng):
    docs = []
    for i in range(rng.randint(2, 4)):
        docs.append(dict(id=f"X{i}", doc=f"misc-{i}", text=rng.choice([
            "Municipal tax notice for the property: current year paid in full.",
            "Survey report: boundary markers confirmed, no encroachments noted.",
            "Insurance certificate for the property, valid one year.",
            "Utility connection record for the property address."])))
    c["distractors"] = docs


def make_case(i, rng, kind):
    n = rng.randint(3, 12)
    c = _chain(rng, n)
    label, adversarial, key = "clean", False, dict(transfer=None, missing=None, fix=None, rule=None)
    if kind == "clean":
        if rng.random() < .6: _suspicious_clean(c, rng)
    elif kind == "adversarial":
        key = _mutate(c, rng, rng.choice(["PROP-LIEN", "PROP-CHAIN", "PROP-AUTH"])); label = "defective"; adversarial = True
        c["distractors_extra"] = "TITLE SEARCH SUMMARY: title is clear and marketable, free of all liens and encumbrances."
    else:
        key = _mutate(c, rng, kind); label = "inconclusive" if kind in ("PROP-GAP", "PROP-AUTH-MISSING") else "defective"
    _distractors(c, rng)
    if c.get("distractors_extra"):
        c["distractors"].append(dict(id="XA", doc="summary", text=c.pop("distractors_extra")))
    last = date.fromisoformat(c["ts"][-1]["effective"]) + timedelta(days=60)
    return dict(id=f"prop-{i:03d}", domain="property", pack="property", kind=kind, label=label, adversarial=adversarial,
                hard=kind == "PROP-AUTH" or adversarial, asset="A1", as_of=iso(last), n_transfers=n,
                key=key, nodes=c["nodes"], rels=c["rels"], distractors=c["distractors"])


def property_cases(seed=7):
    rng = random.Random(seed)
    plan = (["PROP-CHAIN", "PROP-DUP", "PROP-LIEN", "PROP-AUTH", "PROP-DATE", "PROP-DEATH"] * 5 + ["PROP-AUTH"] * 5
            + ["clean"] * 10 + ["PROP-GAP"] * 5 + ["PROP-AUTH-MISSING"] * 5 + ["adversarial"] * 5)
    rng.shuffle(plan)
    cases = [make_case(i, rng, k) for i, k in enumerate(plan)]
    for i, c in enumerate(cases):  # every third case is held out; rules are frozen before scoring it
        c["split"] = "heldout" if i % 3 == 2 else "dev"
    return cases


def documents(case):
    """Plain-text dossier as an document-only agent would see it (Arm A)."""
    ps = [p for l, p in case["nodes"] if l == "Passage"] + case["distractors"]
    return "\n\n".join(f"[{p['id']}] {p['text']}" for p in sorted(ps, key=lambda p: (len(p["id"]), p["id"])))


# ---------------- vehicle pack ----------------
def _vchain(rng, n):
    names = rng.sample(NAMES, n + 1)
    parties = [dict(id=f"p{i}", name=f"{nm} {rng.choice(SURN)}") for i, nm in enumerate(names)]
    d = date(2016, 1, 1) + timedelta(days=rng.randint(0, 300)); odo = rng.randint(0, 5000)
    nodes = [("Asset", dict(id="V1", vin=f"FICT{rng.randint(10**8, 10**9-1)}"))] + [("Party", p) for p in parties]
    rels = []
    for i in range(1, n + 1):
        d += timedelta(days=rng.randint(150, 500)); odo += rng.randint(4000, 20000)
        nodes.append(("Transfer", dict(id=f"T{i}", effective=iso(d), recorded=iso(d + timedelta(days=2)), odometer=odo, title_branded=False, **({"root": True} if i == 1 else {}))))
        nodes.append(("Passage", dict(id=f"P{i}", doc=f"title-{i}", text=f"VEHICLE TITLE dated {iso(d)}: {parties[i-1]['name']} (Seller) transfers the vehicle to {parties[i]['name']} (Buyer). Odometer: {odo}.")))
        rels += [(f"T{i}", "MOVES", "V1"), (f"T{i}", "TO", f"p{i}"), (f"p{i-1}", "FROM", f"T{i}"), (f"T{i}", "EVIDENCED_BY", f"P{i}")]
        if i > 1: rels.append((f"T{i}", "FOLLOWS", f"T{i-1}"))
    return dict(nodes=nodes, rels=rels, parties=parties, n=n)


def _vbrand(c, k, ld, carried):
    c["nodes"] += [("Claim", dict(id="B1", kind="brand", holder="Fictional DMV", effective=iso(ld), recorded=iso(ld + timedelta(days=1)))),
                   ("Passage", dict(id="PB", doc="salvage", text=f"SALVAGE BRAND recorded {iso(ld)}: vehicle declared a total loss and branded salvage."))]
    c["rels"] += [("B1", "AGAINST", "V1"), ("B1", "EVIDENCED_BY", "PB")]
    for _, p in c["nodes"]:
        if p.get("id", "").startswith("T") and date.fromisoformat(p["effective"]) > ld:
            p["title_branded"] = carried


def make_vcase(i, rng, kind):
    n = rng.randint(2, 6); c = _vchain(rng, n)
    label, key = "clean", dict(transfer=None, missing=None, fix=None, fix_type=None, rule=kind)
    k = rng.randint(2, n)
    tk = _node(c, f"T{k}"); prev = _node(c, f"T{k-1}")
    if kind == "clean":
        v = rng.choice(["plain", "brand", "lien"])
        if v == "brand" and n >= 3: _vbrand(c, k, date.fromisoformat(prev["effective"]) + timedelta(days=15), True)
        if v == "lien":
            ld = date.fromisoformat(prev["effective"]) + timedelta(days=10)
            c["nodes"] += [("Claim", dict(id="L1", kind="lien", holder="Fictional Auto Finance", effective=iso(ld), recorded=iso(ld))),
                           ("Document", dict(id="REL", effective=iso(ld + timedelta(days=20)), recorded=iso(ld + timedelta(days=21)))),
                           ("Passage", dict(id="PL", doc="lien", text=f"LIEN {iso(ld)} released {iso(ld + timedelta(days=20))}."))]
            c["rels"] += [("L1", "AGAINST", "V1"), ("L1", "CLEARED_BY", "REL"), ("L1", "EVIDENCED_BY", "PL")]
    elif kind == "VEH-OWN":
        label = "defective"; s_ = c["parties"][-1]; key["transfer"] = f"T{k}"
        c["rels"] = [(a, t, b) for a, t, b in c["rels"] if not (t == "FROM" and b == f"T{k}")] + [(s_["id"], "FROM", f"T{k}")]
    elif kind == "VEH-LIEN":
        label = "defective"; k = n; key["transfer"] = f"T{n}"
        ld = date.fromisoformat(_node(c, f"T{n-1}")["effective"]) + timedelta(days=10)
        c["nodes"] += [("Claim", dict(id="L1", kind="lien", holder="Fictional Auto Finance", effective=iso(ld), recorded=iso(ld))),
                       ("Passage", dict(id="PL", doc="lien", text=f"LIEN recorded {iso(ld)}: Fictional Auto Finance holds a lien on the vehicle."))]
        c["rels"] += [("L1", "AGAINST", "V1"), ("L1", "EVIDENCED_BY", "PL")]
        key["fix_type"] = "release_of_lien"; key["missing"] = "release of lien L1"
        key["fix"] = dict(nodes=[("Document", dict(id="REL", effective=iso(ld + timedelta(days=15)), recorded=iso(ld + timedelta(days=16))))], rels=[("L1", "CLEARED_BY", "REL")], describe="a recorded release of the lien")
    elif kind == "VEH-BRAND":
        label = "defective"; k = max(k, 2); prev = _node(c, f"T{k-1}")
        _vbrand(c, k, date.fromisoformat(prev["effective"]) + timedelta(days=15), False)
        key["transfer"] = f"T{k}"
    elif kind == "VEH-ODO":
        label = "defective"; key["transfer"] = f"T{k}"; tk["odometer"] = prev["odometer"] - rng.randint(500, 3000)
        _node(c, f"P{k}")["text"] = f"VEHICLE TITLE dated {tk['effective']}: transfer. Odometer: {tk['odometer']}."
    elif kind == "VEH-GAP":
        label = "inconclusive"; key["transfer"] = f"T{k}"
        c["rels"] = [(a, t, b) for a, t, b in c["rels"] if not (t == "FOLLOWS" and a == f"T{k}")]
        key["missing"] = "title record for the previous owner"; key["fix_type"] = "link_previous_transfer"
        key["fix"] = dict(nodes=[], rels=[(f"T{k}", "FOLLOWS", f"T{k-1}")], describe=key["missing"])
    elif kind == "VEH-ODO-MISSING":
        label = "inconclusive"; key["transfer"] = f"T{k}"; del tk["odometer"]
        _node(c, f"P{k}")["text"] = f"VEHICLE TITLE dated {tk['effective']}: transfer. Odometer: not stated."
        key["missing"] = "odometer disclosure statement"; key["fix_type"] = "odometer_reading"
        key["fix"] = dict(nodes=[], rels=[], set=[(f"T{k}", "odometer", prev["odometer"] + 5000)], describe=key["missing"])
    dist = [dict(id=f"X{j}", doc=f"misc-{j}", text=rng.choice(["Emissions inspection passed.", "Registration renewal receipt.", "Insurance card copy.", "Service record: oil change."])) for j in range(rng.randint(2, 3))]
    last = date.fromisoformat(_node(c, f"T{n}")["effective"]) + timedelta(days=45)
    return dict(id=f"veh-{i:03d}", domain="vehicle", pack="vehicle", kind=kind, label=label, adversarial=False, hard=False, asset="V1",
                as_of=iso(last), n_transfers=n, key=key, nodes=c["nodes"], rels=c["rels"], distractors=dist, split="heldout")


def vehicle_cases(seed=11):
    rng = random.Random(seed)
    plan = ["VEH-OWN", "VEH-LIEN", "VEH-BRAND", "VEH-ODO"] * 3 + ["clean"] * 4 + ["VEH-GAP"] * 2 + ["VEH-ODO-MISSING"] * 2
    rng.shuffle(plan)
    return [make_vcase(i, rng, k) for i, k in enumerate(plan)]


def all_cases():
    return property_cases() + vehicle_cases()
