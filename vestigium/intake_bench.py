"""Extraction benchmark: can a reader rebuild the graph from the dossier, and does the engine then reach the right verdict?

Readers: 'regex' (canonical wording only, free, offline) and 'llm' (Gemini). Styles: 'clean' and 'messy'.
Scored against the gold graph. Resumable; stops cleanly when the daily quota is spent.
  uv run python -m vestigium.intake_bench --readers regex llm --styles clean messy --repeats 1
"""
import argparse, json, pathlib, statistics, time
from .dossier import dossier
from .engine import run_checks
from .extract import read_rules, read_llm, assemble
from .generator import all_cases
from .llm import DailyQuotaExhausted
from .whatif import build

FIELDS = {"deed": ["date", "recorded", "from", "to", "root", "follows", "signed_by_agent", "authority"],
          "title": ["date", "recorded", "from", "to", "root", "follows", "signed_by_agent", "authority", "odometer", "title_branded"],
          "authority": ["agent", "valid_from", "valid_to"], "lien": ["holder", "date", "recorded"], "brand": ["holder", "date", "recorded"],
          "release": ["date", "recorded", "releases"], "death": ["person", "died", "recorded"]}
norm = lambda v: None if v in (None, "", False) else v


def gold_ir(case):
    return read_rules(dossier(case, "clean"))        # exact on clean text, so it is the answer key for extraction


def score_ir(case, ir):
    """Field accuracy over the facts the rules read, record-exact rate, and whether the engine's finding matches gold."""
    gold = {r["id"]: r for r in gold_ir(case)["records"]}
    got = {r.get("id"): r for r in (ir or {}).get("records", [])}
    fields = ok = rec_ok = rec_n = 0
    for rid, g in gold.items():
        if g["type"] not in FIELDS: continue
        rec_n += 1; all_ok = True
        for f in FIELDS[g["type"]]:
            fields += 1
            match = got.get(rid, {}).get("type") == g["type"] and norm(got.get(rid, {}).get(f)) == norm(g.get(f))
            ok += match; all_ok &= match
        rec_ok += all_ok
    return dict(field_acc=ok / fields if fields else 1, record_exact=rec_ok / rec_n if rec_n else 1)


def judge(case, ir):
    """Verdict from the engine on the extracted graph; findings keyed by the record that evidences the transfer."""
    try:
        g = assemble(ir, as_of=case["as_of"])
        res = run_checks(build(g), g["asset"], g["as_of"], pack=g["pack"])
    except Exception as e:                          # a reader that returns a malformed graph is a failed extraction
        return None, set(), str(e)[:120]
    t2rec = {a: b for a, t, b in g["rels"] if t == "EVIDENCED_BY" and a.startswith("T")}
    where = {(f["rule"], t2rec.get(f["transfer"])) for f in res["findings"] + res["missing"]}
    return res["verdict"], where, None


def gold_where(case):
    t2rec = {a: b for a, t, b in case["rels"] if t == "EVIDENCED_BY" and a.startswith("T")}
    res = run_checks(build(case), case["asset"], case["as_of"], pack=case["pack"])
    return {(f["rule"], t2rec.get(f["transfer"])) for f in res["findings"] + res["missing"]}


def run_one(case, reader, style, rep):
    text = dossier(case, style, seed=rep)
    t = time.time(); st = dict(tokens=0, model_calls=0)
    if reader == "regex": ir = read_rules(text)
    else: ir, st = read_llm(text)
    verdict, where, err = judge(case, ir) if ir else (None, set(), "no IR")
    sc = score_ir(case, ir)
    return dict(reader=reader, style=style, case=case["id"], rep=rep, label=case["label"], verdict=verdict, correct=verdict == case["label"],
                false_clean=(verdict == "clean") if case["label"] == "defective" else None,
                located=where == gold_where(case), error=err, tokens=st.get("tokens", 0), secs=round(time.time() - t, 1), **sc)


def report(rows):
    pct = lambda S, k: f"{100*statistics.mean(float(r[k]) for r in S):5.1f}%" if S else "   -"
    print(f"{'reader':7}{'style':7}{'n':>4}{'verdict-acc':>13}{'false-clean':>13}{'located':>9}{'field-acc':>11}{'record-exact':>14}{'tokens':>9}")
    for rd in sorted({r["reader"] for r in rows}):
        for sty in ("clean", "messy"):
            R = [r for r in rows if r["reader"] == rd and r["style"] == sty]
            if not R: continue
            D = [r for r in R if r["false_clean"] is not None]
            print(f"{rd:7}{sty:7}{len(R):>4}{pct(R,'correct'):>13}{pct(D,'false_clean'):>13}{pct(R,'located'):>9}{pct(R,'field_acc'):>11}{pct(R,'record_exact'):>14}{int(statistics.mean(r['tokens'] for r in R)):>9}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readers", nargs="+", default=["regex"]); ap.add_argument("--styles", nargs="+", default=["clean", "messy"])
    ap.add_argument("--repeats", type=int, default=1); ap.add_argument("--split", default="heldout"); ap.add_argument("--out", default="results")
    a = ap.parse_args()
    cases = [c for c in all_cases() if a.split == "all" or c["split"] == a.split]
    f = pathlib.Path(a.out) / "intake.jsonl"; f.parent.mkdir(exist_ok=True)
    rows = [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []
    done = {(r["reader"], r["style"], r["case"], r["rep"]) for r in rows if not r["error"] or r["reader"] == "regex"}
    rows = [r for r in rows if (r["reader"], r["style"], r["case"], r["rep"]) in done]
    for rd in a.readers:
        for sty in a.styles:
            for c in cases:
                for rep in range(a.repeats):
                    if (rd, sty, c["id"], rep) in done: continue
                    try: rows.append(run_one(c, rd, sty, rep))
                    except DailyQuotaExhausted as e:
                        print("STOP:", e); f.write_text("\n".join(json.dumps(x) for x in rows)); return report(rows)
                    except Exception as e:
                        rows.append(dict(reader=rd, style=sty, case=c["id"], rep=rep, label=c["label"], verdict=None, correct=False, false_clean=None, located=False,
                                         error=str(e)[:120], tokens=0, secs=0, field_acc=0, record_exact=0))
                    if rd == "llm": f.write_text("\n".join(json.dumps(x) for x in rows))
    f.write_text("\n".join(json.dumps(x) for x in rows)); report(rows)


if __name__ == "__main__":
    main()
