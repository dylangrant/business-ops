"""Fixed monthly shares (rent, T-Mobile via Venmo, USAA renters portion) recorded once per month."""
from datetime import date
from decimal import Decimal

from bookkeeping.allocate import allocate
from bookkeeping.ledger import Entry, Ledger


def rate_for(rates: list[dict], month: str) -> Decimal | None:
    applicable = [r for r in rates if r["from"] <= month]
    return Decimal(max(applicable, key=lambda r: r["from"])["amount"]) if applicable else None


def record_month(rules: dict, ledger: Ledger, month: str) -> list[dict]:
    y, m = map(int, month.split("-"))
    out = []
    for f in rules.get("fixed_monthly", []):
        when = date(y, m, f.get("day", 1))
        source = f"fixed:{f['key']}:{month}"
        amount = rate_for(f["rates"], month)
        if amount is None:
            ledger.add(Entry(name=f["name"], category="", txn_date=when, amount=Decimal("0"), adjusted=Decimal("0"),
                             deductible=Decimal("0"), notes=f"no rate on file for {month}; add one to rules.yaml",
                             source=source, status="needs_review"))
            out.append({"key": f["key"], "status": "needs_review"})
            continue
        a = allocate(rules, f["vendor"], amount)
        added = ledger.add(Entry(name=f["name"], category=a.category, txn_date=when, amount=amount, adjusted=a.adjusted_amount,
                                 deductible=a.deductible, notes=f"{a.share * 100:.0f}% business share (fixed monthly)",
                                 paid_from=f.get("paid_from", a.paid_from or ""), due_to_owner=a.deductible,
                                 document=f.get("document", ""), source=source))
        out.append({"key": f["key"], "status": "recorded" if added else "duplicate", "share": str(a.deductible)})
    return out
