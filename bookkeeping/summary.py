"""Monthly summary email for the owner, built from the ledger."""
import base64
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from bookkeeping.ledger import Ledger

MAX_ATTACH_BYTES = 18 * 1024 * 1024
MIME = {".pdf": "application/pdf", ".txt": "text/plain"}


def _attach(ledger: Ledger, docs: list[str]) -> tuple[list[dict], list[str], list[str]]:
    """Returns (attachments, missing names, over-limit names). Relative paths resolve under ledger.root."""
    attachments, missing, skipped, total = [], [], [], 0
    for doc in dict.fromkeys(docs):
        path = Path(doc)
        if not path.is_absolute():
            path = ledger.root / path
        if not path.is_file():
            missing.append(path.name)
            continue
        size = path.stat().st_size
        if skipped or total + size > MAX_ATTACH_BYTES:
            skipped.append(path.name)
            continue
        total += size
        attachments.append({"filename": path.name, "mimeType": MIME.get(path.suffix.lower(), "application/octet-stream"),
                            "data": base64.b64encode(path.read_bytes()).decode("ascii")})
    return attachments, missing, skipped


def build(ledger: Ledger, month: str) -> dict:
    """month = 'YYYY-MM'. Returns {subject, body, attachments} (attachments = [{filename, mimeType, data(base64)}] for that month's bill files)."""
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
    docs = [r["Document"] for r in sorted(recorded, key=lambda r: r["Transaction Date"]) if r["Document"]]
    attachments, missing, skipped = _attach(ledger, docs)
    if attachments:
        lines += ["", "Bills attached:"] + [f"  {a['filename']}" for a in attachments]
    if missing:
        lines += ["", "Missing files: " + ", ".join(missing)]
    if skipped:
        lines += ["", "Not attached (size limit): " + ", ".join(skipped)]
    return {"subject": subject, "body": "\n".join(lines) + "\n", "attachments": attachments}
