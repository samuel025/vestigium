"""Property rule pack: deterministic Cypher checks. Each rule returns rows
{transfer, detail, evidence} with `as_of` (valid time) and `known` (record time)
parameters, so a chain can be replayed as it was true and as it was known."""

# Visibility filter used by every rule: effective on/before as_of, recorded on/before known.
VIS = "t.effective <= date($as_of) AND t.recorded <= date($known)"

# Real definitions (TO is Transfer->Party, FROM is Party->Transfer per the plan).
PROPERTY_RULES = {
    "PROP-CHAIN": dict(kind="defect", text="Grantor was not the previous grantee", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}}), (g:Party)-[:FROM]->(t),
      (t)-[:FOLLOWS]->(p:Transfer)-[:TO]->(prev:Party)
WHERE {VIS} AND p.recorded <= date($known) AND g <> prev
RETURN t.id AS transfer, g.name + ' sold but ' + prev.name + ' was the previous grantee' AS detail,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "PROP-GAP": dict(fix_type="link_previous_transfer", kind="gap", text="Gap in the chain", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}})
WHERE {VIS} AND coalesce(t.root,false) = false AND NOT (t)-[:FOLLOWS]->(:Transfer)
RETURN t.id AS transfer, 'No record links this transfer to a previous owner' AS detail,
       'record showing how ' + [(g:Party)-[:FROM]->(t) | g.name][0] + ' acquired the asset' AS missing,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "PROP-DUP": dict(kind="defect", text="Same property sold twice", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}}), (t2:Transfer)-[:MOVES]->(:Asset {{id:$asset}}),
      (g:Party)-[:FROM]->(t), (g)-[:FROM]->(t2)
WHERE {VIS} AND t2.effective <= date($as_of) AND t2.recorded <= date($known)
  AND t.id < t2.id AND NOT (t2)-[:FOLLOWS*]->(t)
RETURN t2.id AS transfer, g.name + ' conveyed the asset in both ' + t.id + ' and ' + t2.id AS detail,
       [(t2)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] + [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "PROP-DATE": dict(kind="defect", text="Deed dated before grantor acquired the property", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}}), (t)-[:FOLLOWS]->(p:Transfer)
WHERE {VIS} AND t.effective < p.effective
RETURN t.id AS transfer, 'Deed dated ' + toString(t.effective) + ' precedes grantor acquisition on ' + toString(p.effective) AS detail,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "PROP-LIEN": dict(fix_type="release_of_lien", kind="defect", text="Lien never released", cypher=f"""
MATCH (c:Claim)-[:AGAINST]->(:Asset {{id:$asset}}), (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}})
WHERE {VIS} AND c.kind = 'lien' AND c.effective < t.effective AND c.recorded <= date($known)
  AND NOT EXISTS {{ (c)-[:CLEARED_BY]->(d:Document) WHERE d.effective <= t.effective AND d.recorded <= date($known) }}
RETURN t.id AS transfer, c.id + ' (' + c.holder + ') was open at transfer' AS detail,
       [(c)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "PROP-AUTH": dict(fix_type="valid_authority", kind="defect", text="Authority not valid on signing date", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}}), (t)-[:ACTED_UNDER]->(au:Authority)
WHERE {VIS} AND NOT EXISTS {{ (t)-[:ACTED_UNDER]->(ok:Authority)
        WHERE ok.valid_from <= t.effective AND (ok.valid_to IS NULL OR ok.valid_to >= t.effective) }}
RETURN t.id AS transfer, au.agent + ' signed on ' + toString(t.effective) + ' but authority ran ' +
       toString(au.valid_from) + ' to ' + coalesce(toString(au.valid_to),'open') AS detail,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] + [(au)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "PROP-AUTH-MISSING": dict(fix_type="valid_authority", kind="gap", text="Signed by an agent with no authority record", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}})
WHERE {VIS} AND t.by_agent = true AND NOT (t)-[:ACTED_UNDER]->(:Authority)
RETURN t.id AS transfer, 'Signed by an agent but no authority record exists' AS detail,
       'power of attorney or resolution authorising the signatory' AS missing,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "PROP-DEATH": dict(kind="defect", text="Grantor deceased at signing", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}}), (g:Party)-[:FROM]->(t)
WHERE {VIS} AND g.died IS NOT NULL AND g.died < t.effective AND g.died_recorded <= date($known)
RETURN t.id AS transfer, g.name + ' died ' + toString(g.died) + ' before signing' AS detail,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),
}


VEHICLE_RULES = {
    "VEH-OWN": dict(kind="defect", fix_type=None, text="Seller is not the titled owner", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}}), (g:Party)-[:FROM]->(t),
      (t)-[:FOLLOWS]->(p:Transfer)-[:TO]->(prev:Party)
WHERE {VIS} AND g <> prev
RETURN t.id AS transfer, g.name + ' sold but ' + prev.name + ' is the titled owner' AS detail,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "VEH-LIEN": dict(kind="defect", fix_type="release_of_lien", text="Lien not released", cypher=f"""
MATCH (c:Claim)-[:AGAINST]->(:Asset {{id:$asset}}), (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}})
WHERE {VIS} AND c.kind = 'lien' AND c.effective < t.effective AND c.recorded <= date($known)
  AND NOT EXISTS {{ (c)-[:CLEARED_BY]->(d:Document) WHERE d.effective <= t.effective AND d.recorded <= date($known) }}
RETURN t.id AS transfer, c.id + ' (' + c.holder + ') was open at sale' AS detail,
       [(c)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "VEH-BRAND": dict(kind="defect", fix_type=None, text="Salvage brand not carried forward", cypher=f"""
MATCH (c:Claim)-[:AGAINST]->(:Asset {{id:$asset}}), (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}})
WHERE {VIS} AND c.kind = 'brand' AND c.effective < t.effective AND c.recorded <= date($known) AND t.title_branded = false
RETURN t.id AS transfer, 'Title issued ' + toString(t.effective) + ' omits the salvage brand recorded ' + toString(c.effective) AS detail,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] + [(c)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "VEH-ODO": dict(kind="defect", fix_type=None, text="Odometer reading falls between transfers", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}}), (t)-[:FOLLOWS]->(p:Transfer)
WHERE {VIS} AND t.odometer IS NOT NULL AND p.odometer IS NOT NULL AND t.odometer < p.odometer
RETURN t.id AS transfer, 'Odometer ' + toString(t.odometer) + ' is below the earlier reading ' + toString(p.odometer) AS detail,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "VEH-GAP": dict(kind="gap", fix_type="link_previous_transfer", text="Gap in the title chain", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}})
WHERE {VIS} AND coalesce(t.root,false) = false AND NOT (t)-[:FOLLOWS]->(:Transfer)
RETURN t.id AS transfer, 'No title record links this sale to the previous owner' AS detail,
       'title record showing how ' + [(g:Party)-[:FROM]->(t) | g.name][0] + ' acquired the vehicle' AS missing,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),

    "VEH-ODO-MISSING": dict(kind="gap", fix_type="odometer_reading", text="Odometer reading missing", cypher=f"""
MATCH (t:Transfer)-[:MOVES]->(:Asset {{id:$asset}})
WHERE {VIS} AND t.odometer IS NULL
RETURN t.id AS transfer, 'No odometer reading recorded at this transfer' AS detail,
       'odometer disclosure statement for this transfer' AS missing,
       [(t)-[:EVIDENCED_BY]->(ps:Passage) | ps.id] AS evidence"""),
}
