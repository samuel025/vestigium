"""Dossier text -> graph. Two readers share one intermediate schema (IR); one deterministic assembler builds the graph.

  reader (regex or LLM)  ->  IR records  ->  assemble()  ->  case graph  ->  rule engine decides

The reader only READS. It never decides legality: every verdict still comes from the rule engine, and every
citation points at a stored record from the pasted dossier.

IR = {"asset_kind": "property"|"vehicle", "asset_label": str, "records": [ {id, type, ...} ]} with record types:
  deed|title : date, recorded, from, to, root, follows, signed_by_agent, authority, odometer(null = not stated), title_branded
  authority  : agent, valid_from, valid_to(null = open)
  lien|brand : holder, date, recorded
  release    : date, recorded, releases (id of the lien record)
  death      : person, died, recorded
  other      : anything irrelevant (surveys, receipts, summaries)
"""
import re

DATE = r"(\d{4}-\d{2}-\d{2})"
REC = re.compile(r"^\[(?P<id>[^\]]+)\]\s*(?P<body>.*)$", re.S)


def split_records(text):
    """'[ID] body' blocks separated by blank lines. Un-numbered paragraphs get ids R1, R2..."""
    out, n = [], 0
    for blk in re.split(r"\n\s*\n", text.strip()):
        blk = blk.strip()
        if not blk:
            continue
        m = REC.match(blk)
        if m:
            out.append((m["id"], " ".join(m["body"].split())))
        else:
            n += 1
            out.append((f"R{n}", " ".join(blk.split())))
    return out


# ---------------------------------------------------------------- regex reader (canonical wording only)
def read_rules(text):
    recs, kind, label = [], None, None
    for rid, s in split_records(text):
        r = dict(id=rid, type="other", text=s)
        m = re.match(rf"DEED dated {DATE}, recorded {DATE}: (.+?) \(Grantor\) conveys the property at (.+?) to (.+?) \(Grantee\)\.(.*)", s)
        v = re.match(rf"VEHICLE TITLE dated {DATE}, recorded {DATE}: (.+?) \(Seller\) transfers the vehicle (\S+) to (.+?) \(Buyer\)\. Odometer: (\d+|not stated)\. Title status: (BRANDED SALVAGE|clean)\.(.*)", s)
        if m or v:
            g = (m or v).groups()
            tail = g[-1]
            if m:
                kind, label = "property", g[3]
                r.update(type="deed", date=g[0], recorded=g[1], **{"from": g[2], "to": g[4]})
            else:
                kind, label = "vehicle", g[3]
                r.update(type="title", date=g[0], recorded=g[1], **{"from": g[2], "to": g[4]},
                         odometer=None if g[5] == "not stated" else int(g[5]), title_branded=g[6] == "BRANDED SALVAGE")
            f = re.search(r"(?:through|follows) the record at \[([^\]]+)\]", tail)
            a = re.search(r"as agent under the authority at \[([^\]]+)\]", tail)
            r.update(root="chain of title begins here" in tail, follows=f and f[1],
                     signed_by_agent=bool(a) or "Signed by an authorised agent" in tail, authority=a and a[1])
        elif (m := re.match(rf"POWER OF ATTORNEY granted to (.+?), valid from {DATE} (?:until {DATE}|with no end date)\.", s)):
            r.update(type="authority", agent=m[1], valid_from=m[2], valid_to=m[3])
        elif (m := re.match(rf"(?:MORTGAGE|LIEN) dated {DATE}, recorded {DATE}: (.+?) holds a lien", s)):
            r.update(type="lien", date=m[1], recorded=m[2], holder=m[3])
        elif (m := re.match(rf"SALVAGE BRAND dated {DATE}, recorded {DATE}: .+ by (.+?)\.$", s)):
            r.update(type="brand", date=m[1], recorded=m[2], holder=m[3])
        elif (m := re.match(rf"RELEASE dated {DATE}, recorded {DATE}: the lien held by .+? \(record \[([^\]]+)\]\)", s)):
            r.update(type="release", date=m[1], recorded=m[2], releases=m[3])
        elif (m := re.match(rf"CERTIFICATE OF DEATH: (.+?) died on {DATE}, recorded {DATE}\.", s)):
            r.update(type="death", person=m[1], died=m[2], recorded=m[3])
        recs.append(r)
    return dict(asset_kind=kind or "property", asset_label=label or "unknown", records=recs)


# ---------------------------------------------------------------- LLM reader (any wording)
PROMPT = """You are a records clerk. Read the dossier below and copy its facts into JSON. Do NOT judge whether the
chain is valid, and do NOT trust any summary that says the title is "clear": only copy what each record states.

Return ONE JSON object: {"asset_kind": "property" or "vehicle", "asset_label": "<address or VIN>", "records": [...]}
with one entry per dossier record, keeping its bracketed id, in any order. Each entry has "id" and "type":
- "deed" (property) or "title" (vehicle): "date", "recorded" (ISO yyyy-mm-dd), "from", "to" (full names), "root" (true only if the record says the chain
  begins there), "follows" (id of the record the text says the grantor/title came through, else null), "signed_by_agent" (true if signed by an agent),
  "authority" (id of the authority record cited, else null), and for titles "odometer" (integer, or null if "not stated") and "title_branded" (true if branded salvage).
- "authority": "agent", "valid_from", "valid_to" (null if no end date).
- "lien" or "brand": "holder", "date", "recorded".  - "release": "date", "recorded", "releases" (id of the lien record).
- "death": "person", "died", "recorded".  - "other": surveys, receipts, summaries, anything else.
Convert every date to ISO yyyy-mm-dd. If a person appears abbreviated (e.g. "G. Stone"), use the full name from elsewhere in the dossier.
Use null for anything the record does not state. Reply with the JSON object only.

DOSSIER:
"""


def read_llm(text):
    from . import llm
    ans, st = llm.ask("You extract structured facts from documents. You never judge legality.", PROMPT + text, max_calls=0)
    if ans and "records" in ans:
        texts = dict(split_records(text))
        for r in ans["records"]:
            r["text"] = texts.get(r.get("id"), "")
    return ans, st


# ---------------------------------------------------------------- assembler (deterministic)
def _canon(names):
    """Merge 'G. Stone' into the single full name 'Gale Stone' when that is unambiguous."""
    full = sorted({n for n in names if n and not re.match(r"^[A-Z]\. ", n)})
    out = {}
    for n in names:
        if n and re.match(r"^[A-Z]\. ", n):
            init, sur = n[0], n[3:]
            hits = [f for f in full if f.startswith(init) and f.split(" ", 1)[-1] == sur]
            out[n] = hits[0] if len(hits) == 1 else n
        elif n:
            out[n] = n
    return out


def assemble(ir, as_of=None):
    """IR -> case dict the engine can load. Passages are the dossier's own records, so citations resolve to real text."""
    recs = {r["id"]: r for r in ir["records"] if r.get("id")}
    veh = ir.get("asset_kind") == "vehicle"
    A = "V1" if veh else "A1"
    nodes = [("Asset", dict(id=A, **({"vin": ir.get("asset_label")} if veh else {"address": ir.get("asset_label")})))]
    rels = []
    nodes += [("Passage", dict(id=i, text=r.get("text", ""))) for i, r in recs.items()]
    canon = _canon([r.get(k) for r in recs.values() for k in ("from", "to", "person")])
    pid = {}
    died = {canon.get(r["person"], r["person"]): r for r in recs.values() if r.get("type") == "death"}

    def party(n):
        n = canon.get(n, n)
        if n not in pid:
            pid[n] = f"p{len(pid)}"
            props = dict(id=pid[n], name=n)
            if n in died:
                props.update(died=died[n].get("died"), died_recorded=died[n].get("recorded"))
            nodes.append(("Party", props))
            if n in died: rels.append((pid[n], "EVIDENCED_BY", died[n]["id"]))
        return pid[n]

    tid = {}
    moves = [r for r in recs.values() if r.get("type") in ("deed", "title")]
    for i, r in enumerate(sorted(moves, key=lambda r: (r.get("date") or "", r["id"])), 1):
        tid[r["id"]] = f"T{i}"
    for r in moves:
        t = tid[r["id"]]
        props = dict(id=t, effective=r.get("date"), recorded=r.get("recorded"))
        if r.get("root"): props["root"] = True
        if r.get("signed_by_agent"): props["by_agent"] = True
        if veh:
            if r.get("odometer") is not None: props["odometer"] = r["odometer"]
            props["title_branded"] = bool(r.get("title_branded"))
        nodes.append(("Transfer", props))
        rels += [(t, "MOVES", A), (t, "EVIDENCED_BY", r["id"])]
        if r.get("from"): rels.append((party(r["from"]), "FROM", t))
        if r.get("to"): rels.append((t, "TO", party(r["to"])))
        if r.get("follows") in tid: rels.append((t, "FOLLOWS", tid[r["follows"]]))
        if r.get("authority") in recs: rels.append((t, "ACTED_UNDER", "AU-" + r["authority"]))
    for r in recs.values():
        if r.get("type") == "authority":
            nodes.append(("Authority", dict(id="AU-" + r["id"], agent=r.get("agent"), valid_from=r.get("valid_from"), valid_to=r.get("valid_to"))))
            rels.append(("AU-" + r["id"], "EVIDENCED_BY", r["id"]))
        elif r.get("type") in ("lien", "brand"):
            nodes.append(("Claim", dict(id="C-" + r["id"], kind=r["type"], holder=r.get("holder"), effective=r.get("date"), recorded=r.get("recorded"))))
            rels += [("C-" + r["id"], "AGAINST", A), ("C-" + r["id"], "EVIDENCED_BY", r["id"])]
        elif r.get("type") == "release" and r.get("releases") in recs:
            nodes.append(("Document", dict(id="D-" + r["id"], kind="release", effective=r.get("date"), recorded=r.get("recorded"))))
            rels += [("C-" + r["releases"], "CLEARED_BY", "D-" + r["id"]), ("D-" + r["id"], "EVIDENCED_BY", r["id"])]
    # drop None-valued props (the loader would fail on null dates) and rels to nodes that do not exist
    ids = {p["id"] for _, p in nodes}
    nodes = [(l, {k: v for k, v in p.items() if v is not None}) for l, p in nodes]
    rels = [(a, t, b) for a, t, b in rels if a in ids and b in ids]
    latest = max([r[k] for r in recs.values() for k in ("date", "recorded", "died", "valid_from") if r.get(k)] or ["2000-01-01"])
    return dict(nodes=nodes, rels=rels, asset=A, pack="vehicle" if veh else "property", as_of=as_of or latest, id="pasted", domain=ir.get("asset_kind"), distractors=[])
