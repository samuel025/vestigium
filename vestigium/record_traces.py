"""Record full agent transcripts (every tool call, its arguments and result, and the final answer) for a showcase set.

The benchmark's results/heldout.jsonl keeps each run's answer and call counts. This keeps the whole conversation for the cases the
demo replays, so the UI can show what the agent actually did. Arm A reads documents only; Arm C calls the rule engine's tools.
  uv run python -m vestigium.record_traces
"""
import json, pathlib, sys
from .arms import arm_a, arm_c
from .bench import valid_passages
from .generator import all_cases, documents
from .llm import DailyQuotaExhausted

SHOWCASE = ["prop-014", "prop-059", "prop-006", "prop-013", "prop-019", "prop-029", "prop-003", "prop-051", "veh-003", "veh-011", "veh-017", "veh-012"]
OUT = pathlib.Path("results/traces.jsonl")


def main(ids=SHOWCASE):
    cases = {c["id"]: c for c in all_cases()}
    rows = [json.loads(l) for l in OUT.read_text().splitlines()] if OUT.exists() else []
    done = {(r["case"], r["arm"]) for r in rows if not r.get("error")}
    rows = [r for r in rows if (r["case"], r["arm"]) in done]
    for cid in ids:
        c = cases[cid]
        for arm, fn in (("A", arm_a), ("C", arm_c)):
            if (cid, arm) in done: continue
            try: ans, st = fn(c)
            except DailyQuotaExhausted as e:
                print("STOP:", e); OUT.write_text("\n".join(json.dumps(r) for r in rows)); return
            except Exception as e:
                print(cid, arm, "error", str(e)[:100]); continue
            ok = valid_passages(c)
            cites = [dict(id=e, valid=e in ok, text=next((p["text"] for l, p in c["nodes"] if l == "Passage" and p["id"] == e), None)) for e in (ans or {}).get("evidence", [])]
            rows.append(dict(case=cid, arm=arm, label=c["label"], answer=ans, trace=st.get("trace", []), final_text=st.get("final_text"), citations=cites,
                             tokens=st.get("tokens"), model_calls=st.get("model_calls"), tool_calls=st.get("tool_calls"), error=None))
            OUT.write_text("\n".join(json.dumps(r) for r in rows))
            print(cid, arm, "->", (ans or {}).get("verdict"), "| label", c["label"], "| tool calls", st.get("tool_calls"))


if __name__ == "__main__":
    main()
