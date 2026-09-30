import csv
from decimal import Decimal
from pathlib import Path

import pytest

from bookkeeping.allocate import NoRule, allocate, load_rules

FIXTURE = Path(__file__).parent / "fixtures" / "ledger_2025_ph27.csv"
# Rows where the filed 2025 ledger differs from the rule (owner confirmed rules are right): (vendor, date) -> filed amount
KNOWN_DIFFS = {("Amazon", "2025-12-22", "janitorial"): Decimal("1.60"),   # 5% of 30.00 is 1.50
               ("1Password", "2025-05-05", ""): Decimal("30.00")}          # 50% of 59.85 is 29.93
RULES = load_rules()


def rows():
    return list(csv.DictReader(FIXTURE.open()))


def test_fixture_covers_ph27_2025():
    assert len(rows()) == 73  # all ph27 rows of the 2025 ledger except ChatGPT (subscription retired)


@pytest.mark.parametrize("r", rows(), ids=lambda r: f"{r['vendor']} {r['date']} {r['item_category']}")
def test_2025_ledger_row(r):
    a = allocate(RULES, r["vendor"], r["gross"], r["business_subtotal"] or None, r["item_category"] or None)
    key = (r["vendor"], r["date"], r["item_category"])
    filed = Decimal(r["expected_deductible"])
    if key in KNOWN_DIFFS:
        assert filed == KNOWN_DIFFS[key] and a.deductible != filed
    else:
        assert a.deductible == filed


def test_known_diffs_are_exactly_the_documented_ones():
    assert allocate(RULES, "Amazon", "30.00", "30.00", "janitorial").deductible == Decimal("1.50")
    assert allocate(RULES, "1Password", "59.85").deductible == Decimal("29.93")


def test_claude_is_fully_business():
    a = allocate(RULES, "Anthropic, PBC (Claude)", "20.00")
    assert (a.category, a.deductible) == ("Dues and Subscriptions", Decimal("20.00"))


def test_unknown_vendor_and_mixed_without_items_raise():
    with pytest.raises(NoRule):
        allocate(RULES, "Random Store", "10.00")
    with pytest.raises(NoRule):
        allocate(RULES, "Amazon", "10.00")


def test_office_share_matches_square_footage():
    h = RULES["home_office"]
    assert Decimal(h["business_sqft"]) / Decimal(h["home_sqft"]) == Decimal("0.05")
