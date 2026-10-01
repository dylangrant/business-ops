"""Monthly summary email for the owner, built from the ledger."""
from collections import defaultdict
from decimal import Decimal

from bookkeeping.ledger import Ledger


def build(ledger: Ledger, month: str) -> dict:
    """month = 'YYYY-MM'. Returns {subject, body, attachments} (attachments = bill PDF paths for that month)."""
    rows = ledger.rows()
    month_rows = [r for r in rows if r["Transaction Date"].startswith(month)]
    recorded = [r for r in month_rows if r["Status"] == "recorded"]
    review = [r for r in rows if r["Status"] == "needs_review"]          # all open reviews, any month
    by_cat: dict[str, Decimal] = defaultdict(Decimal)
    for r in recorded:
        by_cat[r["Category"]] += Decimal(r["Prorated Deductible Amount"])
    owed_month = sum((Decimal(r["Due To Owner"]) for r in recorded), Decimal("0"))
    balance = ledger.balance_owed()

    lines = [f"ph27 bills for {month}", ""]
    if recorded:
        lines.append("Recorded:")
        for r in sorted(recorded, key=lambda r: r["Transaction Date"]):
            lines.append(f"  {r['Transaction Date']}  {r['Name']:<24} gross ${r['Amount']:>9}  ph27 share ${r['Prorated Deductible Amount']:>8}"
                         + ("" if Decimal(r["Due To Owner"]) else "  (paid by ph27)"))
        lines += ["", "By category:"] + [f"  {c:<28} ${v:.2f}" for c, v in sorted(by_cat.items())]
    else:
        lines.append("No bills recorded for this month.")
    lines += ["", f"Owed to you for {month}: ${owed_month:.2f}", f"Total owed to you (unreimbursed): ${balance:.2f}"]
    if review:
        lines += ["", f"Needs you ({len(review)}):"]
        lines += [f"  {r['Transaction Date']}  {r['Name']}: {r['Notes'] or 'see ledger'}" for r in review]
    subject = f"ph27 bills {month}: ${owed_month:.2f} owed to you" + (f", {len(review)} need you" if review else "")
    attachments = [r["Document"] for r in recorded if r["Document"]]
    return {"subject": subject, "body": "\n".join(lines) + "\n", "attachments": attachments}
