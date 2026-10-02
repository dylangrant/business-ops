from decimal import Decimal

from bookkeeping.allocate import load_rules
from bookkeeping.fixed import rate_for, record_month
from bookkeeping.ledger import Ledger

RULES = load_rules()


def test_rate_history():
    rates = [{"from": "2025-04", "amount": "68.52"}, {"from": "2026-10", "amount": "66.16"}]
    assert rate_for(rates, "2026-09") == Decimal("68.52")
    assert rate_for(rates, "2026-10") == Decimal("66.16")
    assert rate_for(rates, "2025-03") is None


def test_record_month_and_idempotent(tmp_path):
    l = Ledger(tmp_path)
    r = {x["key"]: x for x in record_month(RULES, l, "2026-10")}
    assert r["rent"]["share"] == "176.00" and r["t_mobile"]["share"] == "3.75" and r["insurance"]["share"] == "3.31"
    assert all(x["status"] == "duplicate" for x in record_month(RULES, l, "2026-10"))
    assert len(l.rows()) == 3 and l.balance_owed() == Decimal("183.06")


def test_month_before_first_rate_needs_review(tmp_path):
    l = Ledger(tmp_path)
    r = {x["key"]: x for x in record_month(RULES, l, "2025-03")}     # before ph27 existed: no rates
    assert r["insurance"]["status"] == "needs_review" and r["rent"]["status"] == "needs_review"
    r = {x["key"]: x for x in record_month(RULES, l, "2026-06")}
    assert r["insurance"]["share"] == "3.43"
