"""Turn one bill email into a ledger row (recorded or needs_review). Code owns rules, math, files."""
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from bookkeeping.allocate import allocate
from bookkeeping.ledger import Entry, Ledger
from bookkeeping.verify import check_bill

LABELED_AMOUNT = re.compile(
    r"(?:amount\s+(?:due|paid|charged)|total(?:\s+(?:due|charged|paid))?|balance\s+due|you\s+paid|payment\s+amount)"
    r"[^\d$]{0,30}\$?\s?(\d{1,3}(?:,\d{3})+|\d+)\.(\d{2})", re.I)


@dataclass
class Email:
    id: str
    sender: str
    subject: str
    date: date
    text: str
    links: list[str] = field(default_factory=list)


def vendor_for(rules: dict, sender: str, subject: str = "", text: str = "") -> dict | None:
    """Match on the sender; for a forwarded email, on a vendor domain in the body. An optional
    per-vendor `subject` regex keeps a vendor's non-bill mail (bank alerts, promos) out."""
    s = sender.lower()
    forwarded = any(f in s for f in rules.get("forwarders", []))
    hay = text.lower()[:5000] if forwarded else s
    for v in rules["vendors"]:
        if any(m in hay for m in v.get("senders", [])):
            if v.get("subject") and not re.search(v["subject"], subject, re.I):
                return None
            return v
    return None


def amount_from_email(text: str) -> Decimal | None:
    """Only a LABELED total counts (amount due / total / amount paid); several different ones -> None."""
    found = {Decimal(m.group(1).replace(",", "") + "." + m.group(2)) for m in LABELED_AMOUNT.finditer(text)}
    return found.pop() if len(found) == 1 else None


def _parse_date(s: str, fallback: date) -> date:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def process(email: Email, rules: dict, ledger: Ledger, fetcher=None, media_dir: Path | None = None) -> dict:
    v = vendor_for(rules, email.sender, email.subject, email.text)
    if not v:
        return {"status": "ignored", "reason": f"no vendor rule for sender {email.sender}"}
    name = v["match"][0].title() if v["key"] != "internet" else "Quantum Fiber"
    name = {"rent": "Rent", "t_mobile": "T-Mobile", "onepassword": "1Password", "nw_natural": "NW Natural",
            "zenbusiness": "ZenBusiness"}.get(v["key"], name)
    owner_paid = v.get("owner_paid", True)

    def review(reason: str, amount=Decimal("0"), when=email.date, doc=""):
        ledger.add(Entry(name=name, category=v["category"], txn_date=when, amount=amount, adjusted=Decimal("0"),
                         deductible=Decimal("0"), notes=reason, paid_from=v.get("paid_from", ""), document=doc,
                         source=email.id, status="needs_review"))
        return {"status": "needs_review", "vendor": name, "reason": reason}

    if v.get("portal", True) and fetcher is not None:
        start = v.get("start_url") or (email.links[0] if email.links else "")
        if not start:
            return review("no start URL for the bill portal")
        r = fetcher.run(name, start, v["vault"], hint=f"The bill email arrived {email.date.isoformat()}.")
        if r.get("status") != "saved":
            return review(f"bill fetch {r.get('status')}: {r.get('notes', '')}"[:200])
        when = _parse_date(r.get("billDate", ""), email.date)
        try:
            amount = Decimal(str(r.get("amountTotal")))
        except (InvalidOperation, TypeError):
            return review("agent reported no usable amount", when=when)
        pdf = Path(str(r.get("pdfPath", "")).removeprefix("FILE:"))
        if media_dir is not None:
            pdf = media_dir / pdf.name
        ok, why = check_bill(pdf, amount)
        if not ok:
            return review(why, amount=amount, when=when)
        doc = ledger.file_bill(pdf, name, when, amount)
    else:
        amount = amount_from_email(email.text)
        when = email.date
        doc_dir = ledger.root / "Bills" / f"{when:%m}"
        doc_dir.mkdir(parents=True, exist_ok=True)
        doc = doc_dir / f"{when.isoformat()}_{v['key']}_email_{email.id}.txt"
        doc.write_text(f"From: {email.sender}\nSubject: {email.subject}\nDate: {email.date}\n\n{email.text}")
        if amount is None:
            return review("no single labeled total in the email; enter by hand", doc=str(doc))

    a = allocate(rules, name if v["key"] != "rent" else "rent", amount)
    added = ledger.add(Entry(name=name, category=a.category, txn_date=when, amount=amount, adjusted=a.adjusted_amount,
                             deductible=a.deductible, notes=f"{a.share * 100:.0f}% business share",
                             paid_from=v.get("paid_from", ""), due_to_owner=a.deductible if owner_paid else Decimal("0"),
                             document=str(doc), source=email.id))
    return {"status": "recorded" if added else "duplicate", "vendor": name, "amount": str(amount), "share": str(a.deductible)}
