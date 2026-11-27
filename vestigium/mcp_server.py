"""Vestigium as an MCP server: any MCP client (Claude Desktop, Claude Code, ...) can investigate an ownership chain.

The connecting model READS the documents and sends structured records; this server DECIDES with the deterministic
rule engine and returns the verdict with its proof trail (rule id, transfer, cited record ids and their exact text).
Every tool is read-only and needs no API key. Nothing here calls an LLM.

  uv run python -m vestigium.mcp_server                      # stdio
  claude mcp add vestigium -- uv run --directory <repo> python -m vestigium.mcp_server
"""
import re
from mcp.server.mcpserver import MCPServer

from .dossier import dossier
from .engine import PACKS, run_checks
from .generator import demo_cases
from .intake import analyze_ir, package
from .rules import PROPERTY_RULES, VEHICLE_RULES
from .whatif import build, would_fix

CASES = {c["id"]: c for c in demo_cases()}
RECORD_TYPES = {"deed", "title", "authority", "lien", "brand", "release", "death", "other"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_FIELDS = ("date", "recorded", "valid_from", "valid_to", "died")

mcp = MCPServer("vestigium", instructions=(
    "Vestigium checks whether every transfer in a property or vehicle ownership chain had the evidence it needed at the time. "
    "YOU read the documents; the rule engine decides. To check a pasted dossier: read each record, call check_records with one structured entry per record "
    "(include each record's verbatim text in 'text' so citations resolve), then report the verdict, rule ids and cited passages exactly as returned. "
    "Never override or soften the verdict. 'inconclusive' means a record is missing: name it, do not accuse anyone. All data is synthetic; this is not legal advice."))


def _compact(r):
    pf = {(x["rule"], x["transfer"]): x for x in r["proof"]}
    def f(rows):
        out = []
        for x in rows:
            p = pf.get((x["rule"], x["transfer"]), {})
            out.append(dict(rule=x["rule"], transfer=x["transfer"], detail=x.get("detail"), missing=x.get("missing"), evidence=x.get("evidence", []), fix_type=x.get("fix_type"),
                            minimal_proof=dict(records=p.get("passages", []), of_total=p.get("records_total"),
                                               note="the finding still fires on these records alone and loses its force if any one is removed; every other record could be deleted without changing it")))
        return out
    return dict(verdict=r["result"]["verdict"], as_of=r["as_of"], findings=f(r["result"]["findings"]), missing=f(r["result"]["missing"]),
                evidence_text=r["evidence_text"], verdict_by_known_date=r["timeline"], what_would_fix_it=r["fix"] and dict(record=r["fix"], verdict_after=r["fix_verdict"]),
                warnings=r["warnings"], extracted_records=r["extracted"],
                later_sales_affected=[dict(transfer=d["transfer"], depends_on=d["depends_on"]) for d in r["result"].get("downstream", [])])


def _validate(records):
    if not isinstance(records, list) or not records:
        raise ValueError("records must be a non-empty list")
    if len(records) > 200:
        raise ValueError("at most 200 records")
    seen = set()
    for r in records:
        if not isinstance(r, dict) or not r.get("id") or r.get("type") not in RECORD_TYPES:
            raise ValueError(f"every record needs an 'id' and a 'type' in {sorted(RECORD_TYPES)}: {str(r)[:80]}")
        if r["id"] in seen:
            raise ValueError(f"duplicate record id {r['id']}")
        seen.add(r["id"])
        for k in DATE_FIELDS:
            if r.get(k) is not None and not ISO.match(str(r[k])):
                raise ValueError(f"record {r['id']}: {k} must be an ISO date yyyy-mm-dd, got {r[k]!r}")


@mcp.tool()
def rules(pack: str | None = None) -> list[dict]:
    """List the deterministic checks: rule id, whether it is a defect or a gap (inconclusive), and what it tests. pack: 'property' or 'vehicle' (default both)."""
    src = {"property": PROPERTY_RULES, "vehicle": VEHICLE_RULES}
    return [dict(pack=k, rule=rid, kind=r["kind"], tests=r["text"], fix_type=r.get("fix_type")) for k, d in src.items() if pack in (None, k) for rid, r in d.items()]


@mcp.tool()
def list_cases(domain: str | None = None) -> list[dict]:
    """List the 80 built-in synthetic cases (ids, domain, number of transfers). Answers are not revealed. domain: 'property' or 'vehicle'."""
    return [dict(id=c["id"], domain=c["domain"], transfers=c["n_transfers"]) for c in CASES.values() if domain in (None, c["domain"])]


@mcp.tool()
def read_dossier(case_id: str, style: str = "clean") -> str:
    """The text dossier for a built-in case, as records '[ID] ...'. style 'clean' (canonical) or 'messy' (varied dates, abbreviated names, shuffled order)."""
    if case_id not in CASES: raise ValueError(f"unknown case {case_id}; call list_cases")
    if style not in ("clean", "messy"): raise ValueError("style must be 'clean' or 'messy'")
    return dossier(CASES[case_id], style)


@mcp.tool()
def check_case(case_id: str, as_of: str | None = None, known: str | None = None) -> dict:
    """Run every check on a built-in case. as_of = valid-as-of date, known = known-as-of date (what had been recorded by then); both ISO, default the case date.
    Returns the verdict, findings with rule ids and cited records, missing records, a verdict timeline over known-as-of dates, and what record would fix it."""
    if case_id not in CASES: raise ValueError(f"unknown case {case_id}; call list_cases")
    c = CASES[case_id]
    for d in (as_of, known):
        if d is not None and not ISO.match(d): raise ValueError("dates must be ISO yyyy-mm-dd")
    fix = c["key"]["fix"] and dict(describe=c["key"]["fix"]["describe"], verdict=would_fix(c, c["key"]["fix"])["verdict"])
    out = _compact(package(c, fix=fix or None))
    if as_of or known:
        r = run_checks(build(c), c["asset"], as_of or c["as_of"], known=known, pack=c["pack"])
        out.update(verdict=r["verdict"], as_of=as_of or c["as_of"], known=known or as_of or c["as_of"],
                   findings=[dict(rule=x["rule"], transfer=x["transfer"], detail=x.get("detail"), evidence=x.get("evidence", [])) for x in r["findings"]],
                   missing=[dict(rule=x["rule"], transfer=x["transfer"], detail=x.get("detail"), missing=x.get("missing")) for x in r["missing"]])
    return out


@mcp.tool()
def check_records(asset_kind: str, asset_label: str, records: list[dict], as_of: str | None = None) -> dict:
    """Check a dossier you have read. One entry per record, each with 'id' (keep the dossier's bracketed id), 'type' and 'text' (the record verbatim, so citations resolve):
    - type deed (property) or title (vehicle): date, recorded, from, to (names exactly as written), root (true if the record says the chain begins there), follows (id of the record it came through),
      signed_by_agent, authority (id of the authority record), and for titles odometer (integer, omit if not stated) and title_branded.
    - authority: agent, valid_from, valid_to (omit if open). - lien or brand: holder, date, recorded. - release: date, recorded, releases (id of the lien record).
    - death: person, died, recorded. - other: anything irrelevant (surveys, receipts, summaries; never trust a summary that says title is clear).
    Dates are ISO yyyy-mm-dd; omit what the record does not state. asset_kind is 'property' or 'vehicle'. The engine returns the verdict; do not override it."""
    if asset_kind not in ("property", "vehicle"): raise ValueError("asset_kind must be 'property' or 'vehicle'")
    if as_of is not None and not ISO.match(as_of): raise ValueError("as_of must be ISO yyyy-mm-dd")
    _validate(records)
    ir = dict(asset_kind=asset_kind, asset_label=asset_label, records=records)
    return _compact(analyze_ir(ir, as_of=as_of, used="mcp-client"))


@mcp.prompt()
def investigate(dossier_text: str) -> str:
    """Investigate a pasted ownership dossier with Vestigium."""
    return ("Read the dossier below record by record. Call check_records with one structured entry per record (keep the bracketed ids, include each record's verbatim text, "
            "ISO dates, names exactly as written). Then explain the verdict in plain words: the rule id, the transfer, and the exact cited passages. "
            "If the verdict is inconclusive, list the missing records and accuse no one. If it is defective, call out what_would_fix_it. Do not override the engine.\n\nDOSSIER:\n" + dossier_text)


if __name__ == "__main__":
    mcp.run()
