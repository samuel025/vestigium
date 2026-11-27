"""Render a full-fidelity dossier (every graph fact stated in text) from a gold case, for the intake pipeline.

Unlike generator.documents() (used by the benchmark's Arm A and left untouched), nothing the rules need is
missing from this text: recorded dates, who signed as agent, authority dates, liens, releases, deaths, odometers.
So an extractor that reads it correctly can rebuild a graph the engine judges identically to the gold graph.
style="clean" is the canonical wording a regex parser can read; style="messy" varies date formats, abbreviates
names and shuffles record order, which only a reader that understands language (the LLM) handles reliably.
"""
import random
from datetime import date

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _fmt(iso, style, rng):
    if not iso or style == "clean":
        return iso
    d = date.fromisoformat(iso)
    return rng.choice([iso, f"{d.day} {MONTHS[d.month-1]} {d.year}", f"{MONTHS[d.month-1][:3]} {d.day}, {d.year}"])


def _short(name, style, rng):
    if style == "messy" and rng.random() < .35:
        a, b = name.split(" ", 1)
        return f"{a[0]}. {b}"
    return name


def dossier(case, style="clean", seed=0):
    rng = random.Random(f"{seed}-{case['id']}-{style}")
    nodes = {p["id"]: (l, p) for l, p in case["nodes"] if "id" in p}
    rel = lambda a, t: [b for x, tt, b in case["rels"] if x == a and tt == t]
    frm = lambda tid: [a for a, t, b in case["rels"] if t == "FROM" and b == tid]
    rec = lambda nid: next(iter(rel(nid, "EVIDENCED_BY")), None)           # id of the record that states this fact
    asset = nodes[case["asset"]][1]
    veh = case["domain"] == "vehicle"
    what = f"vehicle {asset['vin']}" if veh else f"property at {asset['address']}"
    F = lambda iso: _fmt(iso, style, rng)
    recs = []

    for tid, (lab, t) in nodes.items():
        if lab != "Transfer":
            continue
        g, r_ = nodes[frm(tid)[0]][1]["name"], nodes[rel(tid, "TO")[0]][1]["name"]
        g, r_ = _short(g, style, rng), _short(r_, style, rng)
        if veh:
            s = (f"VEHICLE TITLE dated {F(t['effective'])}, recorded {F(t['recorded'])}: {g} (Seller) transfers the {what} to {r_} (Buyer). "
                 f"Odometer: {t['odometer'] if 'odometer' in t else 'not stated'}. Title status: {'BRANDED SALVAGE' if t.get('title_branded') else 'clean'}.")
        else:
            s = f"DEED dated {F(t['effective'])}, recorded {F(t['recorded'])}: {g} (Grantor) conveys the {what} to {r_} (Grantee)."
        if t.get("root"):
            s += " This is the first recorded transfer; the chain of title begins here."
        for u in rel(tid, "FOLLOWS"):
            s += f" Grantor acquired title through the record at [{rec(u)}]." if not veh else f" This title follows the record at [{rec(u)}]."
        if t.get("by_agent"):
            au = rel(tid, "ACTED_UNDER")
            s += (f" Signed by {t.get('signer') or nodes[au[0]][1]['agent']} as agent under the authority at [{rec(au[0])}]." if au
                  else " Signed by an authorised agent on behalf of the Grantor.")
        recs.append((rec(tid), s))

    for nid, (lab, p) in nodes.items():
        if lab == "Authority":
            to = f"until {F(p['valid_to'])}" if p.get("valid_to") else "with no end date"
            gb = [nodes[x][1]["name"] for x in rel(nid, "GRANTED_BY")]
            scope = {"sell": ", authorising the sale of the property", "management": ", authorising the management and letting of the property only"}.get(p.get("scope"), "")
            recs.append((rec(nid), f"POWER OF ATTORNEY granted {'by ' + gb[0] + ' ' if gb else ''}to {p['agent']}, valid from {F(p['valid_from'])} {to}{scope}."))
            for rv in rel(nid, "REVOKED_BY"):
                rd = nodes[rv][1]
                recs.append((rec(rv), f"REVOCATION dated {F(rd['effective'])}, recorded {F(rd['recorded'])}: the power of attorney at [{rec(nid)}] is revoked."))
        elif lab == "Claim":
            pid = rec(nid)
            if p["kind"] == "brand":
                recs.append((pid, f"SALVAGE BRAND dated {F(p['effective'])}, recorded {F(p['recorded'])}: vehicle declared a total loss and branded salvage by {p['holder']}."))
            else:
                recs.append((pid, f"{'LIEN' if veh else 'MORTGAGE'} dated {F(p['effective'])}, recorded {F(p['recorded'])}: {p['holder']} holds a lien over the {what}."))
                for d in rel(nid, "CLEARED_BY"):
                    dd = nodes[d][1]
                    recs.append((rec(d) or f"{pid}-REL", f"RELEASE dated {F(dd['effective'])}, recorded {F(dd['recorded'])}: the lien held by {p['holder']} (record [{pid}]) is fully discharged."))
        elif lab == "Party" and p.get("died"):
            recs.append((rec(nid), f"CERTIFICATE OF DEATH: {p['name']} died on {F(p['died'])}, recorded {F(p['died_recorded'])}."))

    recs += [(d["id"], d["text"]) for d in case["distractors"]]
    recs = [(i, s) for i, s in recs if i]
    if style == "messy":
        rng.shuffle(recs)
    else:
        recs.sort(key=lambda x: (len(x[0]), x[0]))
    return "\n\n".join(f"[{i}] {s}" for i, s in recs)
