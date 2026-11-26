"""Real records, second city: Philadelphia's Real Estate Transfer Tax records (OpenDataPhilly, `rtt_summary`, public).

    uv run python -m vestigium.philly fetch --n 1000     # deterministic sample of properties -> data/philly_raw/ (gitignored)
    uv run python -m vestigium.philly                    # run the unchanged rules, categorise every finding, write results/philly_real.json

Same honesty rules as the New York test (vestigium/acris.py): deeds are linked in recorded order, the importer (not the
engine) decides whether a seller is the previous buyer with the same stated name match, raw names never leave
data/philly_raw/, and the committed report is anonymised. Sheriff's deeds (foreclosure sales) are a lawful break in the
chain that the synthetic rules do not model, so they are counted separately, not as defects.
"""
import argparse, json, pathlib, random, re, urllib.parse, urllib.request
from collections import Counter
from datetime import date
from .acris import to_case, group_match, tokens
from .engine import run_checks
from .whatif import build

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "philly_raw"
API = "https://phl.carto.com/api/v2/sql"
DEEDS = ("DEED", "DEED SHERIFF", "SHERIFF'S DEED")
TYPES = ",".join("'" + t.replace("'", "''") + "'" for t in DEEDS)


def sql(q, timeout=180):
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode({"q": q}), headers={"User-Agent": "vestigium-research"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["rows"]


def fetch(n=1000, salt="vestigium"):
    """A deterministic pseudo-random sample of single-property parcels with 2+ deeds (ordered by md5, so it is repeatable)."""
    RAW.mkdir(parents=True, exist_ok=True)
    pick = sql(f"""SELECT opa_account_num FROM rtt_summary WHERE document_type IN ({TYPES}) AND property_count = 1
                  AND opa_account_num IS NOT NULL GROUP BY 1 HAVING count(*) >= 2 ORDER BY md5(opa_account_num || '{salt}') LIMIT {int(n)}""")
    ids = [r["opa_account_num"] for r in pick]
    rows = []
    for i in range(0, len(ids), 200):
        chunk = ",".join("'" + x + "'" for x in ids[i:i + 200])
        rows += sql(f"""SELECT opa_account_num, document_id, document_type, document_date, recording_date, grantors, grantees, total_consideration
                        FROM rtt_summary WHERE opa_account_num IN ({chunk}) AND document_type IN ({TYPES}) AND property_count = 1""")
    (RAW / "deeds.json").write_text(json.dumps(rows))
    return len(ids), len(rows)


def split(names):
    return [n.strip() for n in (names or "").split(";") if n.strip()]


def chains():
    rows = json.loads((RAW / "deeds.json").read_text())
    by = {}
    for r in rows:
        if not r.get("recording_date") or not split(r["grantors"]) or not split(r["grantees"]): continue
        by.setdefault(r["opa_account_num"], []).append(r)
    out = []
    for opa, ds in sorted(by.items()):
        ds.sort(key=lambda r: (r["recording_date"], r.get("document_date") or "", r["document_id"]))
        deeds = [dict(id=str(r["document_id"]), type=r["document_type"], recorded=r["recording_date"][:10],
                      effective=(r.get("document_date") or r["recording_date"])[:10], sellers=split(r["grantors"]), buyers=split(r["grantees"]))
                 for r in ds]
        if len(deeds) >= 2: out.append((opa, deeds))
    return out


ESTATE = re.compile(r"\b(EXR|EXRS|EXECUT\w*|ADM|ADMR|ADMX|ADMIN\w*|ESTATE|EST|DECD|DECEASED|HEIRS?|TR|TRS|TRUSTEE|TRUST|GDN|GUARDIAN|POA|ATTY|ATTORNEY)\b")
SHERIFF = re.compile(r"SHERIFF")


def category(deed, prev):
    """Why a seller did not match the previous buyer, by stated heuristics (checked by hand on a sample, see README)."""
    S, B = deed["sellers"], prev["buyers"]
    if SHERIFF.search(deed["type"]) or any(SHERIFF.search(s) for s in S): return "sheriff sale (foreclosure)"
    if any(ESTATE.search(s) for s in S): return "estate, trust or agent sells"
    st = {t for s in S for t in tokens(s) if len(t) >= 4}; bt = {t for b in B for t in tokens(b) if len(t) >= 4}
    if st & bt or _similar(S, B) >= 0.85:
        return ("probable spelling variant in the register (85%+ similar)" if _similar(S, B) >= 0.85
                else "related name, different party (relative, co-owner or sister company)")
    return "no apparent connection"


def explain(review):
    """For each unexplained break, look in the FULL register (every document type, multi-property deeds too) between the
    two deeds for a document that names the seller as grantee. Cached in data/philly_raw/explain.json."""
    f = RAW / "explain.json"
    cache = json.loads(f.read_text()) if f.exists() else {}
    for r in review:
        if r["category"] != "no apparent connection": continue
        key = f"{r['opa']}|{r['deed']['id']}"
        if key not in cache:
            p, d = r["previous"], r["deed"]
            rows = sql(f"""SELECT document_type, property_count, grantors, grantees FROM rtt_summary WHERE opa_account_num='{r['opa']}'
                          AND recording_date > '{p['recorded']}' AND recording_date <= '{d['recorded']}T23:59:59'""")
            cache[key] = [x["document_type"] for x in rows if group_match(split(x["grantees"]), d["sellers"])]
        types = cache[key]
        r["category"] = ("a deed to the seller exists in the full register but not in our extract" if any("DEED" in t for t in types)
                         else "the register shows the seller only as a mortgagor, with no deed to them" if types
                         else "unexplained: no record of how the seller acquired it")
    f.write_text(json.dumps(cache))
    return review


def _similar(S, B):
    """Best character similarity between any seller and any previous buyer. A LABEL for the report only: the matcher
    never accepts a near-miss, because 'KRZSYTOF' vs 'KRZYSZTOF' is for a person to confirm, not for code to assume."""
    from difflib import SequenceMatcher
    from .acris import _flat
    return max((SequenceMatcher(None, _flat(a), _flat(b)).ratio() for a in S for b in B), default=0)


def _days(a, b):
    try: return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except Exception: return None


def run():
    rows, review = [], []
    for k, (opa, deeds) in enumerate(chains(), 1):
        case = to_case(k, deeds)
        res = run_checks(build(case), "A1", case["as_of"], pack="property")
        found = []
        for f in res["findings"] + res["missing"]:
            i = int(f["transfer"][1:])
            cat = (category(deeds[i - 1], deeds[i - 2]) if f["rule"] == "PROP-CHAIN" and i > 1
                   else "recorded out of signing order: signed before the previous deed was signed" if f["rule"] == "PROP-DATE" else f["rule"])
            found.append(dict(rule=f["rule"], transfer=f["transfer"], category=cat))
            review.append(dict(lot=k, opa=opa, rule=f["rule"], category=cat, deed=deeds[i - 1], previous=deeds[i - 2] if i > 1 else None, _f=found[-1]))
        rows.append(dict(lot=k, deeds=len(deeds), verdict=res["verdict"], findings=found,
                         gaps=[_days(d["effective"], d["recorded"]) for d in deeds],
                         signed_before_prev_recorded=sum(b["effective"] < a["recorded"] for a, b in zip(deeds, deeds[1:])),
                         links=[("match" if group_match(b["sellers"], a["buyers"]) else "no match") for a, b in zip(deeds, deeds[1:])]))
    return rows, review


def report(rows, review):
    from statistics import median
    gaps = [g for r in rows for g in r["gaps"] if g is not None and g >= 0]
    links = Counter(l for r in rows for l in r["links"])
    cats = Counter(f["category"] for r in rows for f in r["findings"])
    sheriff_only = sum(1 for r in rows if r["findings"] and all(f["category"].startswith("sheriff") for f in r["findings"]))
    return dict(source="OpenDataPhilly, Real Estate Transfer Tax records (rtt_summary), document types DEED and sheriff's deeds",
                sample="deterministic pseudo-random sample of single-property parcels with 2+ deeds, all years on record",
                properties=len(rows), deeds=sum(r["deeds"] for r in rows), links=sum(links.values()), link_match=dict(links),
                verdicts=dict(Counter(r["verdict"] for r in rows)), findings_by_rule=dict(Counter(f["rule"] for r in rows for f in r["findings"])),
                chain_breaks_by_category=dict(cats.most_common()), defective_only_because_of_sheriff_sales=sheriff_only,
                days_signing_to_recording=dict(median=median(gaps), over_90=sum(g > 90 for g in gaps), over_365=sum(g > 365 for g in gaps), of=len(gaps)),
                signed_before_previous_recorded=sum(r["signed_before_prev_recorded"] for r in rows),
                per_property=[dict(lot=r["lot"], deeds=r["deeds"], verdict=r["verdict"], findings=r["findings"]) for r in rows])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", nargs="?", default="run"); ap.add_argument("--n", type=int, default=1000); a = ap.parse_args()
    if a.cmd == "fetch":
        print("properties, deed rows:", fetch(a.n))
    else:
        rows, review = run()
        for r in explain(review): r["_f"]["category"] = r["category"]
        for r in review: r.pop("_f", None)
        rep = report(rows, review)
        (ROOT / "results" / "philly_real.json").write_text(json.dumps(rep, indent=1))
        (RAW / "review.json").write_text(json.dumps(review, indent=1))
        print(json.dumps({k: v for k, v in rep.items() if k != "per_property"}, indent=1))


def export_app(per_category=4, clean=6):
    """A representative, deterministic selection of Philadelphia properties for the app: a few of every kind of finding,
    plus clean ones. Anonymised like New York (numbered owners, no names, no addresses)."""
    from .acris import app_case
    rows, review = run()
    explain(review)
    cat = {}
    for r in review:
        cat.setdefault(r["lot"], []).append(r["category"])
    picked, seen = [], Counter()
    for k, (opa, deeds) in enumerate(chains(), 1):
        cs = cat.get(k)
        key = cs[0] if cs else "clean"
        if seen[key] < (clean if key == "clean" else per_category):
            seen[key] += 1; picked.append((k, deeds, cs or []))
    out = []
    for k, deeds, cs in picked:
        def notes(r, cs=cs):
            n = [f"Why it was flagged (importer's category, from the full public register): {c}." for c in dict.fromkeys(cs)]
            return n + ["Real public record (Philadelphia Real Estate Transfer Tax records), anonymised. Deeds are linked in recorded order "
                        "and names are matched by the importer; sheriff's deeds are lawful breaks the synthetic rules do not model."]
        c = app_case(k, deeds, f"phl-{k}", f"Philadelphia {k}", "Philadelphia property", notes, None, None, None)
        key = cs[0] if cs else "clean"
        c.update(group=f"Philadelphia · {key}", short=key.split(":")[0].split(" (")[0],
                 headline="Real records: " + ({"clean": "the chain checks out"}.get(key) or key.split(":")[0].split(" (")[0]))
        out.append(c)
    return out
