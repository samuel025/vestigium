# Made-up names in the shapes found in the real register (the real names stay out of the repository).
from vestigium.acris import same, group_match, to_case
from vestigium.engine import run_checks
from vestigium.whatif import build


def test_name_matching_is_stated_and_conservative():
    assert same("ARDEN, MAVIS", "MAVIS ARDEN, AS EXECUTRIX")
    assert same("QUILL, WREN L", "QUILL, WREN")
    assert same("ELM ROW PROPERTIES LLC", "ELM ROW PROPERTIES, LLC")
    assert same("FENWICK, OTTO G", "OTTO GRAY FENWICK")
    assert not same("ARDEN, JUNE ROSE", "MAVIS ARDEN REVOCABLE TRUST")     # same family, different party
    assert not same("DE LAMB, LUC", "DELAMB, LUC")                          # a real kind of variant we deliberately do not guess


def test_a_real_shaped_chain_is_checked_by_the_same_rules():
    d = lambda e, r, s, b: dict(effective=e, recorded=r, sellers=s, buyers=b)
    ok = [d("2004-01-01", "2004-02-01", ["ONE, ANN"], ["SMITH, JANE"]), d("2010-05-01", "2010-06-01", ["SMITH, JANE M"], ["DOE, JOHN"])]
    bad = ok[:1] + [d("2010-05-01", "2010-06-01", ["STRANGER, AL"], ["DOE, JOHN"])]
    for deeds, want in ((ok, "clean"), (bad, "defective")):
        c = to_case(1, deeds)
        assert run_checks(build(c), "A1", c["as_of"])["verdict"] == want
    assert group_match(["NORTH REALTY LLC"], ["NORTH REALTY LLC & SOUTH FUTURE REALTY CORP."])
