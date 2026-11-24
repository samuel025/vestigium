"""Benchmark arms. A: documents only. B: graph + free Cypher. C: graph + rule-engine tools. D: rules alone."""
import json
from .engine import run_checks
from .engine import PACKS
from .generator import documents
from .whatif import build
from .llm import ask


def plain(v):
    """Make Relate results JSON-safe (nodes, relationships, dates)."""
    if hasattr(v, "to_dict"):
        return plain(v.to_dict())
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    return v if isinstance(v, (str, int, float, bool, type(None))) else str(v)

ANSWER = """Reply with ONLY a JSON object:
{"verdict":"clean|defective|inconclusive","rule_id":"<rule or null>","transfer":"<transfer id or null>",
 "evidence":["<passage ids>"],"missing":["<records that are missing, if inconclusive>"],
 "fix_type":"release_of_lien|valid_authority|link_previous_transfer|odometer_reading|none"}
Verdict meanings: clean = no defect; defective = a defect is proven; inconclusive = a missing record prevents a decision
(do not guess and do not accuse anyone). Be careful: a false 'clean' on a defective chain is the worst error."""

SYS = "You are an ownership-chain investigator (property deeds or vehicle titles) for a SYNTHETIC fictional jurisdiction. Not legal advice. " + ANSWER


def arm_a(case):
    p = f"Question as of {case['as_of']}: can the final buyer safely rely on the ownership chain of this property?\n\nDOCUMENTS:\n{documents(case)}"
    return ask(SYS, p)


def arm_b(case):
    db = build(case)
    def read_cypher(query: str) -> list:
        """Run a read-only Cypher query on the ownership graph. Nodes: Asset{id}, Party{name,died}, Transfer{id,effective,recorded,by_agent,odometer,title_branded},
        Claim{kind(lien|brand),holder,effective}, Authority{agent,valid_from,valid_to}, Document, Passage{id,text}. Rels: FROM(Party->Transfer), TO(Transfer->Party),
        MOVES, FOLLOWS(Transfer->previous Transfer), AGAINST, CLEARED_BY, ACTED_UNDER, EVIDENCED_BY, CONTAINS."""
        if any(w in query.upper() for w in ("CREATE", "DELETE", "SET ", "MERGE", "REMOVE")):
            return {"error": "read-only"}
        return plain(db.execute(query).data()[:50])
    return ask(SYS, f"Investigate the graph (asset {case['asset']}) as of {case['as_of']}. Is the chain safe?", tools=[read_cypher])


def arm_c(case):
    db = build(case)
    def list_checks() -> list:
        """List the deterministic rule-engine checks (rule id and what it checks)."""
        return [{"rule": k, "checks": v["text"]} for k, v in PACKS[case["pack"]].items()]
    def run_all_checks(as_of: str = "", known_as_of: str = "") -> dict:
        """Run every rule-engine check. Dates are ISO (YYYY-MM-DD); both default to the question date, so you may call it with no arguments. Returns verdict, findings (with rule, transfer, evidence passage ids) and missing records."""
        as_of = as_of or case["as_of"]
        return run_checks(db, case["asset"], as_of, known_as_of or as_of, pack=case["pack"])
    def read_passage(passage_id: str) -> dict:
        """Read the exact text of a passage by id."""
        return db.execute("MATCH (p:Passage {id:$i}) RETURN p.id AS id, p.text AS text", {"i": passage_id}).data()
    return ask(SYS + "\nUse run_all_checks; the rule engine decides legality. You only investigate and explain. Never invent a rule.",
               f"Investigate asset {case['asset']} as of {case['as_of']}.", tools=[list_checks, run_all_checks, read_passage])


def arm_d(case):
    r = run_checks(build(case), case["asset"], case["as_of"], pack=case["pack"])
    top = (r["findings"] or r["missing"] or [{}])[0]
    return dict(verdict=r["verdict"], rule_id=top.get("rule"), transfer=top.get("transfer"), evidence=top.get("evidence", []),
                missing=[m["missing"] for m in r["missing"]], fix_type=top.get("fix_type") or "none"), dict(tool_calls=0, tool_errors=0, tokens=0)

ARMS = {"A": arm_a, "B": arm_b, "C": arm_c, "D": arm_d}
