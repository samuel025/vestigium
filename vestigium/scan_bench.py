"""Scan benchmark: render each held-out dossier as a scanned PDF / phone photo / poor photo, read it with the vision model,
run the pipeline, and score (a) the verdict, (b) transcription accuracy, and (c) whether low-confidence flags catch the errors.
  uv run python -m vestigium.scan_bench --tiers pdf phone poor
"""
import argparse, json, pathlib, re, statistics, time
from collections import Counter
from .dossier import dossier
from .extract import split_records
from .generator import all_cases
from .intake_bench import gold_where
from .llm import DailyQuotaExhausted
from .scan import render_scan, scan_analyze, TIERS

DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def run_one(case, tier, seed=0):
    text = dossier(case, "clean")
    files, recs = render_scan(text, tier, seed)
    t = time.time()
    out = scan_analyze(files, as_of=case["as_of"])
    if out.get("error"):
        return dict(case=case["id"], tier=tier, label=case["label"], verdict=None, correct=False, error=out["error"], secs=round(time.time() - t, 1))
    got = dict(split_records(out["scan"]["transcript"]))
    flagged = {f["id"]: f["confidence"] for f in out["scan"]["flags"]}
    wrong, silent, n = [], [], 0
    for rid, s in split_records(text):
        n += 1
        ok = Counter(DATE.findall(s)) == Counter(DATE.findall(got.get(rid, "")))      # every date, incl. the stamped recording date, read exactly
        if not ok:
            wrong.append(rid)
            if flagged.get(rid) not in ("low", "medium"): silent.append(rid)
    t2rec = {a: b for a, tt, b in out["rels"] if tt == "EVIDENCED_BY" and a.startswith("T")}
    where = {(f["rule"], t2rec.get(f["transfer"])) for f in out["result"]["findings"] + out["result"]["missing"]}
    v = out["result"]["verdict"]
    return dict(case=case["id"], tier=tier, label=case["label"], verdict=v, correct=v == case["label"],
                false_clean=(v == "clean") if case["label"] == "defective" else None, located=where == gold_where(case),
                records=n, records_wrong=len(wrong), records_silent=len(silent), flagged=len(flagged), warned=bool(out["warnings"]),
                silent_wrong_verdict=(v != case["label"]) and not out["warnings"] and not flagged, reader=out["reader"], pages=out["scan"]["pages"],
                tokens=out["tokens"], secs=round(time.time() - t, 1), error=None)


def report(rows):
    print(f"{'tier':6}{'n':>4}{'verdict':>9}{'false-clean':>13}{'located':>9}{'date-exact recs':>17}{'errors flagged':>16}{'silent wrong verdicts':>23}{'tokens':>8}")
    for tier in TIERS:
        R = [r for r in rows if r["tier"] == tier and not r["error"]]
        if not R: continue
        D = [r for r in R if r["false_clean"] is not None]
        recs = sum(r["records"] for r in R); bad = sum(r["records_wrong"] for r in R); sil = sum(r["records_silent"] for r in R)
        print(f"{tier:6}{len(R):>4}{100*statistics.mean(r['correct'] for r in R):>8.1f}%{100*statistics.mean(r['false_clean'] for r in D) if D else 0:>12.1f}%"
              f"{100*statistics.mean(r['located'] for r in R):>8.1f}%{100*(recs-bad)/recs:>16.1f}%{(f'{bad-sil}/{bad}' if bad else '0/0'):>16}{sum(r['silent_wrong_verdict'] for r in R):>23}{int(statistics.mean(r['tokens'] for r in R)):>8}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tiers", nargs="+", default=list(TIERS)); ap.add_argument("--split", default="heldout")
    ap.add_argument("--limit", type=int); ap.add_argument("--out", default="results"); a = ap.parse_args()
    cases = [c for c in all_cases() if a.split == "all" or c["split"] == a.split][: a.limit]
    f = pathlib.Path(a.out) / "scan.jsonl"; f.parent.mkdir(exist_ok=True)
    rows = [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []
    rows = [r for r in rows if not r["error"]]; done = {(r["case"], r["tier"]) for r in rows}
    for tier in a.tiers:
        for c in cases:
            if (c["id"], tier) in done: continue
            try: rows.append(run_one(c, tier))
            except DailyQuotaExhausted as e:
                print("STOP:", e); break
            except Exception as e:
                rows.append(dict(case=c["id"], tier=tier, label=c["label"], verdict=None, correct=False, error=str(e)[:150], secs=0)); print(c["id"], tier, "error", str(e)[:80])
            f.write_text("\n".join(json.dumps(r) for r in rows))
    f.write_text("\n".join(json.dumps(r) for r in rows)); report(rows)


if __name__ == "__main__":
    main()
