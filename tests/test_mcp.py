"""Talk to the server over a real stdio MCP connection, the way Claude Desktop / Claude Code would."""
import asyncio, json, sys
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

PARAMS = StdioServerParameters(command=sys.executable, args=["-m", "vestigium.mcp_server"])


def data(res):
    if getattr(res, "structured_content", None):
        sc = res.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(res.content[0].text)


async def session():
    async with Client(PARAMS) as c:
        tools = {t.name for t in (await c.list_tools()).tools}
        r = data(await c.call_tool("check_case", {"case_id": "prop-006"}))
        d = await c.call_tool("read_dossier", {"case_id": "prop-014", "style": "clean"})
        text = d.content[0].text
        # the client "reads" the dossier itself (here: our regex reader stands in for the client's model) and sends records
        from vestigium.extract import read_rules
        ir = read_rules(text)
        rr = data(await c.call_tool("check_records", {"asset_kind": ir["asset_kind"], "asset_label": ir["asset_label"], "records": ir["records"]}))
        bad = await c.call_tool("check_records", {"asset_kind": "property", "asset_label": "x", "records": [{"id": "a", "type": "nonsense"}]})
        return tools, r, rr, bad


def test_mcp_roundtrip():
    tools, r, rr, bad = asyncio.run(session())
    assert {"rules", "list_cases", "read_dossier", "check_case", "check_records"} <= tools
    assert r["verdict"] == "defective" and r["findings"][0]["rule"] == "PROP-AUTH"
    assert rr["verdict"] == "defective" and rr["findings"][0]["rule"] == "PROP-AUTH"
    assert all(rr["evidence_text"].get(e) for e in rr["findings"][0]["evidence"])      # every cited record resolves to its exact text
    assert bad.is_error                                                                # invalid input is rejected, not guessed at
