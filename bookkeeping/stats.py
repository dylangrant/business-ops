"""Read-only dashboard numbers for one month (POST /stats). Money rules live in summary.month_totals."""
import re

from bookkeeping.ledger import Ledger
from bookkeeping.summary import month_totals

MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# Recurring bills with no fixed rate: the vendors in these categories bill every month.
MONTHLY_CATEGORIES = {"Utilities"}


def _expected(rules: dict) -> list[dict]:
    """[{name, source_prefix?, match?}]: fixed monthly rows (matched by Source) plus monthly utility vendors (matched by Name)."""
    fixed = [{"name": f["name"], "key": f["key"]} for f in rules.get("fixed_monthly", [])]
    fixed_vendors = {f["vendor"] for f in rules.get("fixed_monthly", [])}
    utilities = [{"name": v["key"], "match": v["match"]} for v in rules.get("vendors", [])
                 if v["category"] in MONTHLY_CATEGORIES and not any(m in fixed_vendors for m in v["match"])]
    return fixed + utilities


def _present(item: dict, month: str, recorded: list[dict]) -> bool:
    if "key" in item:
        return any(r["Source"] == f"fixed:{item['key']}:{month}" for r in recorded)
    return any(any(m in r["Name"].lower() for m in item["match"]) for r in recorded)


def previous_month(month: str) -> str:
    year, number = (int(part) for part in month.split("-"))
    return f"{year - 1}-12" if number == 1 else f"{year}-{number - 1:02d}"


def build(ledger: Ledger, rules: dict, month: str) -> dict:
    """month = 'YYYY-MM': totals for that month, missing bills for the month before
    (this month's bills may not have arrived yet). Raises ValueError on a bad month."""
    if not isinstance(month, str) or not MONTH.match(month):
        raise ValueError("month must be YYYY-MM")
    totals = month_totals(ledger.rows(), month)
    bills_month = previous_month(month)
    bills_recorded = month_totals(ledger.rows(), bills_month)["recorded"]
    missing = [item["name"] for item in _expected(rules) if not _present(item, bills_month, bills_recorded)]
    return {"month": month, "business_spend": f"{totals['spend']:.2f}", "due_to_owner": f"{totals['owed_month']:.2f}",
            "missing_bills": missing, "missing_bills_month": bills_month,
            "needs_review": len(totals["review"])}
