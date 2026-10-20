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


def test_rules_file_renters_change_at_july_2026(tmp_path):
    # rules.yaml: USAA renters 68.52 through 2026-06, 66.16 from 2026-07; month boundary is exact
    l = Ledger(tmp_path)
    june = {x["key"]: x for x in record_month(RULES, l, "2026-06")}
    july = {x["key"]: x for x in record_month(RULES, l, "2026-07")}
    assert june["insurance"]["share"] == "3.43" and july["insurance"]["share"] == "3.31"
    amounts = {r["Transaction Date"]: r["Amount"] for r in l.rows() if r["Name"] == "USAA Renters Insurance"}
    assert amounts == {"2026-06-01": "68.52", "2026-07-01": "66.16"}


def test_backfill_jan_to_sep_is_idempotent(tmp_path):
    l = Ledger(tmp_path)
    months = [f"2026-{m:02d}" for m in range(1, 10)]
    for mo in months:
        record_month(RULES, l, mo)
    first = l.path.read_bytes()
    for mo in months:
        assert all(x["status"] == "duplicate" for x in record_month(RULES, l, mo))
    assert l.path.read_bytes() == first
    assert len(l.rows()) == 27 and l.balance_owed() == Decimal("183.06") * 9 + Decimal("0.12") * 6


def test_needs_review_row_is_replaced_once_a_rate_exists(tmp_path):
    l = Ledger(tmp_path)
    rules = {**RULES, "fixed_monthly": [dict(f) for f in RULES["fixed_monthly"] if f["key"] == "insurance"]}
    rules["fixed_monthly"][0]["rates"] = [{"from": "2026-07", "amount": "66.16"}]
    assert record_month(rules, l, "2026-03")[0]["status"] == "needs_review"
    rules["fixed_monthly"][0]["rates"] = [{"from": "2026-01", "amount": "68.52"}]
    assert record_month(rules, l, "2026-03")[0]["status"] == "recorded"
    assert [r["Status"] for r in l.rows()] == ["recorded"]
