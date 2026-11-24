"""One-command rerun:  uv run python -m vestigium.bench --arms D            (no key needed)
                      GEMINI_API_KEY=... uv run python -m vestigium.bench --arms A B C D --repeats 3 --split heldout"""
import argparse, json, statistics, time, pathlib
from .generator import all_cases
from .whatif import build
from .arms import ARMS
from .llm import DailyQuotaExhausted

def valid_passages(case):
    return {p["id"] for l, p in case["nodes"] if l == "Passage"} | {d["id"] for d in case["distractors"]}

def score(case, out):
    out = out or {}
    v = out.get("verdict"); lab = case["label"]; key = case["key"]
    ev = set(out.get("evidence") or []); ok = valid_passages(case)
    return dict(correct=v == lab, false_clean=((v == "clean") if lab == "defective" else None),
                abstained_ok=(v == "inconclusive") if lab == "inconclusive" else None,
                localized=(out.get("transfer") == key["transfer"]) if lab != "clean" else None,
                citations_valid=all(e in ok for e in ev) if ev else None,
                missing_found=(bool(out.get("missing")) if lab == "inconclusive" else None),
                fix_correct=((out.get("fix_type") == key.get("fix_type")) if key.get("fix_type") else None))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["D"]); ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--split", default="heldout", choices=["dev", "heldout", "all"]); ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    cases = [c for c in all_cases() if a.split == "all" or c["split"] == a.split][: a.limit]
    out = pathlib.Path(a.out); out.mkdir(exist_ok=True)
    f = out / f"{a.split}.jsonl"
    rows = [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []  # resume
    done = {(r["arm"], r["case"], r["rep"]) for r in rows if not (r["stats"] or {}).get("error")}
    rows = [r for r in rows if (r["arm"], r["case"], r["rep"]) in done]
    for arm in a.arms:
        for c in cases:
            for r in range(a.repeats):
                if (arm, c["id"], r) in done:
                    continue
                t = time.time()
                try: ans, st = ARMS[arm](c)
                except DailyQuotaExhausted as e:
                    print("STOP:", e); return report(rows, cases, a)
                except Exception as e: ans, st = None, dict(tool_calls=0, tool_errors=0, tokens=0, error=str(e)[:200])
                rows.append(dict(arm=arm, case=c["id"], rep=r, label=c["label"], hard=c["hard"], answer=ans, stats=st, secs=round(time.time()-t, 1), **score(c, ans)))
                f.write_text("\n".join(json.dumps(x, default=str) for x in rows))  # checkpoint after every run
    report(rows, cases, a)


def report(rows, cases, a):
    ids = {c["id"] for c in cases}
    pct = lambda S, k: (lambda x: f"{100*sum(x)/len(x):.0f}%" if x else "-")([r.get(k) for r in S if r.get(k) is not None])
    print(f"{len(cases)} cases, split={a.split}  (false-clean = share of DEFECTIVE cases called clean; lower is better)")
    print(f"{'arm':6}{'n':>4}{'acc':>7}{'false-clean':>13}{'abstain':>9}{'localize':>10}{'fix-acc':>9}{'cite-ok':>9}{'hard-acc':>10}{'tokens':>9}")
    for arm in a.arms:
        for dom in ["all", "property", "vehicle"]:
            R = [r for r in rows if r["arm"] == arm and r["case"] in ids and (dom == "all" or r["case"].startswith({"property": "prop-", "vehicle": "veh-"}[dom]))]
            if not R: continue
            hard = [r for r in R if r["hard"]]
            tok = int(statistics.mean((r["stats"] or {}).get("tokens", 0) for r in R))
            print(f"{arm + ('' if dom == 'all' else ' ' + dom[:4]):6}{len(R):>4}{pct(R,'correct'):>7}{pct(R,'false_clean'):>13}{pct(R,'abstained_ok'):>9}{pct(R,'localized'):>10}{pct(R,'fix_correct'):>9}{pct(R,'citations_valid'):>9}{pct(hard,'correct'):>10}{tok:>9}")

if __name__ == "__main__":
    main()
